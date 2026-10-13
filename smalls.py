#!/usr/bin/env python3
"""Smalls - Peewee Database Aid."""

# Python Modules
import configparser
import os
import re
import subprocess
import sys
from datetime import datetime
from glob import glob
from importlib import import_module

# PIP Modules
import click
from peewee import AutoField, CharField, DatabaseError, DateTimeField, Model
from playhouse.shortcuts import ThreadSafeDatabaseMetadata
from rich import print as rprint

# Global settings for click
CONTEXT_SETTINGS = {
    "help_option_names": ["-h", "--help"],
    "ignore_unknown_options": True,
}

# Migration files are named NNNN_description.py
MIGRATION_PREFIX_RE = re.compile(r"^(\d{4})_")

# Load the config file
CONFIG = configparser.ConfigParser()
CONFIG.read(os.environ.get("SMALLS_CONFIG", "config.ini"))


def _get_setting(env_var: str, ini_key: str, default: str = "") -> str:
    """Env var first, then config.ini, then the default."""
    value = os.getenv(env_var)
    if value:
        return value
    return CONFIG.get("smalls", ini_key, fallback=default)


def _env_flag(env_var: str) -> bool:
    """True when the env var is set to an affirmative value."""
    return os.getenv(env_var, "").lower() in ("1", "true", "yes", "on")


SMALLS_VERSION = _get_setting("SMALLS_VERSION", "smalls_version", "0.0.0")
MODEL_NAME = _get_setting("SMALLS_MODEL", "model")
OBJECT_NAME = _get_setting("SMALLS_OBJECT", "object", "db")
INIT_SCRIPT = _get_setting("SMALLS_INIT_SCRIPT", "init_script", "initdb.py")
SEED_SCRIPT = _get_setting("SMALLS_SEED_SCRIPT", "seed_script", "seed.py")

# Whether SMALLS_VERSION was actually configured or is just the fallback above.
# `magic` rolls back whenever its version is LOWER than the last stamped one, so a
# process that simply has no config.ini and no env var would otherwise look like a
# downgrade and roll the whole chain back.
SMALLS_VERSION_CONFIGURED = bool(os.getenv("SMALLS_VERSION")) or CONFIG.has_option(
    "smalls", "smalls_version"
)

# `magic` only rolls back when this is set: a schema rollback destroys data, so it
# has to be asked for, never inferred from an image version alone.
ALLOW_AUTO_ROLLBACK = _env_flag("SMALLS_ALLOW_AUTO_ROLLBACK")

if not MODEL_NAME:
    rprint(
        "[red]No model configured. Set `model` in the [smalls] section of "
        "config.ini or the SMALLS_MODEL env var.[/red]"
    )
    sys.exit(1)

# Local models
peewee_model = getattr(import_module(MODEL_NAME), OBJECT_NAME)


# Let's make sure we are ready to handle the migration history via the table
class MigrationHistory(Model):
    """Database Migration History"""

    id = AutoField(primary_key=True)
    name = CharField(unique=True)
    migrated_at = DateTimeField(null=False, default=datetime.now)
    # A string so it can hold a semver such as "1.9.4".
    version = CharField(null=False, max_length=32)

    class Meta:  # pylint: disable=R0903
        """Peewee Configuration"""

        database = peewee_model
        legacy_table_names = False
        model_metadata_class = ThreadSafeDatabaseMetadata


# Check if the MigrationHistory table exists
if not peewee_model.table_exists(MigrationHistory):
    # If the table doesn't exist, create it
    peewee_model.create_tables([MigrationHistory])
    rprint("[red]Table MigrationHistory created.[/red]")


def latest_migration():
    """The furthest migration the database has reached, by number.

    Never a bare `MigrationHistory.select()[-1]`: that is whichever row the
    database happens to hand back last, and physical order stops matching
    migration order after the first rollback -- run_rollback DELETEs history rows
    and a later migrate re-INSERTs them into the freed space. Reading a stale row
    makes `magic` roll back a database that is already current and makes
    `lets_migrate` compute next = last + 1 from the wrong last, re-running an
    applied migration.

    Returns None on an empty history, which every caller reads as "start at the
    top".
    """
    return MigrationHistory.select().order_by(MigrationHistory.name.desc()).first()


@click.group(context_settings=CONTEXT_SETTINGS)
def cli():
    """Peewee Database Manager"""

    rprint("[sky_blue2]=" * 39)
    rprint("[sky_blue2]| Smalls - Peewee Database Manager :thumbs_up: |")
    rprint("[sky_blue2]=" * 39)
    rprint("")
    print("Running at:", datetime.now())


@cli.command()
@click.option("-n", "--number_to_migrate", "number")
def migrate(number=0):
    """Run migrations on the database"""

    if number and not re.fullmatch(r"\d{4}", str(number)):
        rprint(" [red]Number not in correct format! Must be 4 digits.[/red]")
        sys.exit(1)

    # Run a recursive migration
    lets_migrate(number)


@cli.command()
@click.argument("description", required=True)
def create(description):
    """Create a new migration file

    For example:

        ./smalls.py create "adding column foo to table bar"\n
        ./smalls.py create removing_two_columns_from_table_baz
    """

    # Local Vars
    last_number = "0000"

    click.echo("Creating a new file")

    # Get the next file number from the files in the folder
    current_files = sorted(glob("migrations/*.py"))
    if current_files:
        last_number = current_files[-1:][0].split("/")[1][:4]

    # Veriify that we got a number and it's right
    if len(last_number) >= 4:
        try:
            int(last_number)
        except ValueError:
            rprint("[red]Couldn't find a number![/red]")
            sys.exit()
    else:
        rprint("Number found wasn't in the correct format.  Need 4 digits or more.")

    # Prepare the description
    description = description.replace(" ", "_")  # Replace all spaces with underscores
    file_name = (
        "migrations/" + str(int(last_number) + 1).zfill(4) + "_" + description + ".py"
    )

    # Make the file
    create_migration_file(file_name)

    rprint(f" -- Created: [sky_blue2]{file_name}[/sky_blue2]")


@cli.command()
@click.argument("number", required=True)
def rollback(number):
    """Rollback migrations on the database

    The `rollback` command needs a "database version" number
    to rollback too.  The number should be the whole 4 digits.

        smalls.py rollback 1337

    Note: This will set 1337 as the current version of the database.
    It will not run the rollback() inside of the 1337 file.  If you want to
    rollback 1337, set the database version to 1336.

    To go all the way back to the beginning issue the following:

        smalls.py rollback 0000

    """

    if len(number) < 4 or len(number) > 4:
        rprint(" [red]Number not in correct format![/red]")
        print()
        sys.exit(1)

    rprint(f"Rolling back to [dark_orange]{number}[/dark_orange]")
    # abort=True, because the answer used to be discarded: the loop below ran
    # whatever the operator typed.
    click.confirm("Are you sure you want to rollback?", abort=True)
    rprint("Rolling back!")

    # Get the files we've already migrated
    history = MigrationHistory.select().order_by(
        MigrationHistory.migrated_at.desc(), MigrationHistory.id.desc()
    )

    for item in history:  # pylint: disable=not-an-iterable
        item_number = item.name[:4]
        if int(number) < int(item_number):
            run_rollback(item.name)


@cli.command()
def status():
    """Status of the database migrations"""

    # Local vars
    last_number = "0000"

    click.echo("Getting Status...")
    print()

    # Get the last run file
    last_migration = latest_migration()

    # Get the next migration(s) to run
    if last_migration is not None:
        last_number = last_migration.name[:4]

    # Determine if there are more files to run
    migration_files = sorted(glob("migrations/*.py"))

    for file in migration_files:
        file_number = file.split("/")[1][:4]
        if file_number == last_number:
            rprint(
                f"Current Migration: :arrow_right: [green]{file}[/green] :arrow_left:"
            )
        if file_number > last_number:
            rprint(f"Future Migration:    [grey70]{file}[/grey70]")


def _run_script(path):
    """Run a project script, failing loudly if it does.

    os.system discarded the exit status, so `smalls.py seed` exited 0 even when
    the seed script died.
    """
    if not os.path.isfile(path):
        rprint(f"[yellow]{path} not found, nothing to run.[/yellow]")
        return
    try:
        subprocess.run([sys.executable, path], check=True)
    except subprocess.CalledProcessError as error:
        rprint(f"[red]{path} failed with exit code {error.returncode}[/red]")
        sys.exit(error.returncode)


@cli.command()
def init():
    """Initialize the database"""
    click.echo("Initing the database")

    _run_script(INIT_SCRIPT)


@cli.command()
def seed():
    """Load developer seed data into the database"""
    click.echo("Seeding the database")

    _run_script(SEED_SCRIPT)


@cli.command()
def magic():
    """Run magic"""

    last_migration = latest_migration()

    # Migrate if there isn't migrations
    if last_migration is None:
        lets_migrate()
        return

    container_version = version_to_tuple(SMALLS_VERSION)
    database_version = version_to_tuple(last_migration.version)

    # Run migrations (container version is greater than last migration record)
    if container_version > database_version:
        lets_migrate()

    # Run rollback (container version is less than last migration record)
    elif container_version < database_version:
        if not SMALLS_VERSION_CONFIGURED:
            rprint(
                "[red]SMALLS_VERSION is not set (neither env var nor config.ini), "
                f"so the fallback {SMALLS_VERSION!r} is below the last migration "
                f"record ({last_migration.version!r}). Refusing to roll back. "
                "Set SMALLS_VERSION and re-run.[/red]"
            )
            sys.exit(1)
        if not ALLOW_AUTO_ROLLBACK:
            rprint(
                "[red]Container version is behind the last migration record "
                f"({SMALLS_VERSION} < {last_migration.version}). Refusing to "
                "auto-rollback the schema: run `smalls.py rollback <number>` "
                "yourself, or set SMALLS_ALLOW_AUTO_ROLLBACK=true to let magic "
                "do it.[/red]"
            )
            sys.exit(1)
        magic_rollback()
    else:  # Same version: still apply any file the history is missing
        pending = pending_migrations()
        if pending:
            rprint(
                f"[yellow]Version matches but {len(pending)} migration(s) are pending.[/yellow]"
            )
            lets_migrate()
        else:
            rprint(
                "[green]No migration needed. Container version matches the "
                "last migration record.[/green]"
            )


# Utilities ===================================================================
def version_to_tuple(version_str):
    """Convert '1.9.4' to (1, 9, 4) so versions compare numerically.

    Not a string compare: '1.10.0' < '1.9.0' lexically, so `magic` would read a
    minor bump as a downgrade and roll the chain back.

    Anything unparsable sorts below every real version, which puts `magic` on the
    rollback branch -- guarded by SMALLS_VERSION_CONFIGURED and, past that, by
    magic_rollback() refusing a version no migration carries.
    """
    if not version_str:
        return (0,)
    try:
        return tuple(int(part) for part in version_str.split("."))
    except ValueError:
        rprint(
            f"[yellow]Warning: could not parse version {version_str!r} as numbers.[/yellow]"
        )
        return (0,)


def magic_rollback():
    """Run magic rollback"""

    migrations = MigrationHistory.select()
    # `.order_by("asc")` used to stand here, which sorts nothing: peewee binds a
    # bare string as a parameter, so it rendered `ORDER BY %s` with the constant
    # 'asc'. The rollback stops at goal_migration, so an unordered [-1] below
    # picked an arbitrary row among those sharing the version and rolled the chain
    # back past it.
    goal_migrations = (
        migrations.select()
        .where(MigrationHistory.version == SMALLS_VERSION)
        .order_by(MigrationHistory.name.asc())
    )
    # No row carries the target version. Every row is stamped with the version
    # that was current when it ran, so a downgrade below the oldest stamp matches
    # nothing here. Refuse instead of rolling the whole chain back.
    if not goal_migrations:
        rprint(
            f"[red]No migration is stamped with SMALLS_VERSION {SMALLS_VERSION!r}, "
            "so there is nothing to roll back to. Refusing to roll the whole "
            "chain back. Use a SMALLS_VERSION that matches a stamped "
            "migration.[/red]"
        )
        sys.exit(1)

    goal_migration = goal_migrations[-1]
    ordered_migrations = migrations.select().order_by(MigrationHistory.name.desc())

    rprint(f"Rolling back to [dark_orange]{goal_migration.name}[/dark_orange]")

    for item in ordered_migrations:  # pylint: disable=not-an-iterable
        if item.name == goal_migration.name:
            break

        run_rollback(item.name)

    rprint("[green]Rollback finished[/green]")


def run_rollback(file):
    """Run the migration file"""

    # Run the migration file
    print_str = "Rolling back: [dark_orange]" + file + "[/dark_orange]"
    rprint(print_str, end="")
    try:
        migration = import_module("migrations." + file)
        migration.rollback()
        rprint(" [green]Successful[/green]")
    except (DatabaseError, ImportError) as exp:
        rprint(" [red]FAILED[/red]")
        rprint(f" Error was: [yellow1]{exp}[/yellow1]")
        print()  # intentionally print a blank line
        sys.exit(1)  # a half-applied rollback is fatal, and exit 0 hid it

    # Let's tell the database
    MigrationHistory.delete().where(MigrationHistory.name == file).execute()


def migration_file(number):
    """The one migration file numbered `number`, or None if there is none.

    Two files sharing a 4-digit prefix is not a naming quibble, it silently
    drops a migration. Every lookup here is a `glob`, whose order is the
    filesystem's, so one of the two runs, the other never does, and the chain
    then asks for number + 1, does not find it, and reports "Migrations are
    complete".

    It arrives through a merge -- two branches each numbering their migration
    from the same base -- so it appears at merge time, not when either migration
    was written, and the fix is to renumber the one not yet applied anywhere.
    """
    matches = sorted(glob(f"migrations/{number}*.py"))
    if len(matches) > 1:
        rprint(f"[red]More than one migration is numbered {number}:[/red]")
        for match in matches:
            rprint(f"    {match}")
        rprint("[red]Renumber whichever one has not been applied yet.[/red]")
        sys.exit(1)
    return matches[0] if matches else None


def numbered_migration_files():
    """Migration files grouped by their 4-digit number, as {number: [files]}."""
    numbered = {}
    for file in sorted(glob("migrations/*.py")):
        match = MIGRATION_PREFIX_RE.match(os.path.basename(file))
        if match:
            numbered.setdefault(int(match.group(1)), []).append(file)
    return numbered


def validate_migrations_directory():
    """Fail before anything runs if migrations/ has a duplicate number or a gap.

    The chain walks last + 1, so a gap ends it early with "Migrations are
    complete" and everything past the gap is silently never applied.
    """
    numbered = numbered_migration_files()

    duplicates = {n: files for n, files in numbered.items() if len(files) > 1}
    if duplicates:
        rprint("[red]Duplicate migration numbers found:[/red]")
        for number, files in sorted(duplicates.items()):
            rprint(f"  [red]{number:04d}[/red]: {', '.join(files)}")
        rprint("[red]Renumber whichever one has not been applied yet.[/red]")
        sys.exit(1)

    numbers = sorted(numbered)
    if numbers:
        missing = sorted(set(range(numbers[0], numbers[-1] + 1)) - set(numbers))
        if missing:
            rprint(
                "[red]Gap in migrations/: missing "
                f"{', '.join(f'{n:04d}' for n in missing)} "
                f"(have {numbers[0]:04d}..{numbers[-1]:04d}).[/red]"
            )
            sys.exit(1)


def pending_migrations():
    """Numbered migration files that have no MigrationHistory row, in order."""
    applied = {row.name for row in MigrationHistory.select(MigrationHistory.name)}
    return [
        file
        for files in numbered_migration_files().values()
        for file in files
        if file[11:-3] not in applied
    ]


def warn_skipped_migrations():
    """Point out files left behind the last applied migration.

    The chain only moves forward from the highest applied number, so a file
    numbered below it that never ran (merged late, or skipped by `migrate -n`)
    stays unapplied forever unless someone is told.
    """
    skipped = pending_migrations()
    if skipped:
        rprint(
            "[yellow]These migrations are numbered below the last applied one "
            "and were never run:[/yellow]"
        )
        for file in skipped:
            rprint(f"    {file}")
        rprint("[yellow]Run each with `smalls.py migrate -n <number>`.[/yellow]")


def lets_migrate(number=0, recurse=False):
    """Recursive Migration processing"""

    if not recurse:
        validate_migrations_directory()

    # If they passed a number that's the only one we want to run
    if number:
        number_file = migration_file(number)
        if number_file is None:
            rprint(f"[red]No migration numbered {number}[/red]")
            sys.exit(1)
        run_migration(number_file)
        sys.exit()

    # Without a specific number we need to get the files we've already migrated
    last_migration = latest_migration()

    # Get the next migration to run
    if last_migration is not None:
        if not recurse:
            rprint(
                "Last migration was: [i grey69]" + last_migration.name + "[/i grey69]"
            )
            print()
        last_number = last_migration.name[:4]
        next_number = str(int(last_number) + 1).zfill(4)
        next_file = migration_file(next_number)
        if next_file:
            run_migration(next_file)
            lets_migrate(recurse=True)
        else:
            print()
            rprint("  Migrations are complete :tada:")
            warn_skipped_migrations()
    else:
        # Look for the first migration
        all_files = sorted(glob("migrations/*.py"))
        if not all_files:
            print("No files found... nothing to do")
            return
        # By its number, not by name: `all_files[0]` is only the first of a
        # duplicated pair, which is the case this has to refuse rather than run.
        run_migration(migration_file(all_files[0].split("/")[1][:4]))
        lets_migrate(recurse=True)


def run_migration(file):
    """Run the migration file"""

    # Change the file name into a python module name
    module_name = file.split("/")[0] + "." + file.split("/")[1][:-3]

    if not os.path.isfile(file):
        rprint(" [red]Unable to find migration file[/red]")
        rprint(f" {file} not found!")
        sys.exit(1)

    # Run the migration file
    print_str = "Running Migration: [sky_blue2]" + file + "[/sky_blue2]"
    rprint(print_str, end="")
    try:
        migration = import_module(module_name)
        migration.migrate()
        rprint(" [green]Successful[/green]")
    except (DatabaseError, ImportError) as exp:
        rprint(" [red]FAILED[/red]")
        rprint(f" Error was: [yellow1]{exp}[/yellow1]")
        print()  # printing a blank line for readability
        sys.exit(1)  # a failed migration is fatal, never continue

    # Let's tell the database
    MigrationHistory.create(name=file[11:-3], version=SMALLS_VERSION)


def create_migration_file(file_name):
    """Create a migration file template"""

    just_the_file = file_name.split("/")[1]

    file_contents = f'"""{just_the_file}\n\n'
    file_contents += '''Some examples:
# Tables ----------------------------------------------------------------------
# Create a table
from module.model import some_table
db.create_tables([some_table])

# Drop a table
from module.model import some_table
db.drop_tables([some_table])

# Migrator powered commands ---------------------------------------------------
pw_migrate(

    # Basic Table changes =====================================================
    migrator.add_column('some_table', 'title', title_field),
    migrator.rename_column('some_table', 'original_name', 'new_name'),
    migrator.drop_column('some_table', 'column_name'),
    migrator.alter_column_type('some_table', 'column_name', TextField()),
    migrator.rename_table('story', 'stories_tbl')

    # Indexes =================================================================
    # Create an index on the `pub_date` column.
    migrator.add_index('story', ('pub_date',), False),

    # Create a multi-column index on the `pub_date` and `status` fields.
    migrator.add_index('story', ('pub_date', 'status'), False),

    # Create a unique index on the category and title fields.
    migrator.add_index('story', ('category_id', 'title'), True),

    # Remove an index
    migrator.drop_index('story', 'story_pub_date_status')

    # Constraints ==============================================================
    migrator.add_unique('some_table', 'column_name')
    migrator.drop_constraint('some_table', 'constraint_name')

    # Custom constraint
    migrator.add_constraint(
        'products',
        'price_check',
        Check('price >= 0'))
)
"""
# Pylint doesn't like names that start with numbers
# pylint: disable=C0103

from playhouse.migrate import SchemaMigrator
from playhouse.migrate import migrate as pw_migrate

# Model from the config file\n'''
    file_contents += f"from {MODEL_NAME} import {OBJECT_NAME}\n\n"
    # from_database picks the migrator matching the database (Postgres, MySQL, SQLite)
    file_contents += f"migrator = SchemaMigrator.from_database({OBJECT_NAME})"
    file_contents += '''


def migrate():
    """Migration code goes here"""
    pass


def rollback():
    """Rollback code goes here"""
    pass
'''

    # Create the file with the template
    with open(file_name, "w", encoding="utf-8") as template_file:
        template_file.write(file_contents)


if __name__ == "__main__":
    cli()
