#!/usr/bin/env python3
"""
    Smalls - Peewee Database Aid
"""

# Python Modules
import configparser
from datetime import datetime
from importlib import import_module
from glob import glob
import os
import sys

# PIP Modules
import click
from rich import print as rprint

# Global settings for click
CONTEXT_SETTINGS = {
    "help_option_names": ["-h", "--help"],
    "ignore_unknown_options": True,
}

# Load the config file
CONFIG = configparser.ConfigParser()
CONFIG.read("config.ini")

# Local models
peewee_model = import_module(CONFIG["smalls"]["model"])
MigrationHistory = peewee_model.MigrationHistory


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

    The `rollback` command needs a number to rollback too.
    The number should be the whole 4 digits.

        migrate.py rollback 1337

    To go all the way back to the beginning issue the following:

        migrate.py rollback 0000

    """

    if len(number) < 4 or len(number) > 4:
        rprint(" [red]Number not in correct format![/red]")
        print()
        sys.exit()

    rprint(f"Rolling back to [dark_orange]{number}[/dark_orange]")
    if click.confirm("Are you sure you want to rollback?"):
        rprint("Rolling back!")

    # Get the files we've already migrated
    history = MigrationHistory.select().order_by(
        MigrationHistory.migrated_at.desc(), MigrationHistory.id.desc()
    )

    for item in history:
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
    history = MigrationHistory.select().dicts()

    # Get the next migration(s) to run
    if history:
        last_number = history[-1:][0]["name"][:4]

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


@cli.command()
def init():
    """Initialize the database"""
    click.echo("Initing the database")

    if os.path.isfile("initdb.py"):
        os.system("./initdb.py")


@cli.command()
def seed():
    """Load developer seed data into the database"""
    click.echo("Seeding the database")

    if os.path.isfile("seed.py"):
        os.system("./seed.py")


# Utilities ===================================================================
def run_rollback(file):
    """Run the migration file"""

    # Run the migration file
    print_str = "Rolling back: [dark_orange]" + file + "[/dark_orange]"
    rprint(print_str, end="")
    try:
        migration = import_module("migrations." + file)
        migration.rollback()
        rprint(" [green]Successful[/green]")
    except Exception as exp:
        rprint(" [red]FAILED[/red]")
        rprint(f" Error was: [yellow1]{exp}[/yellow1]")
        print()
        sys.exit()

    # Let's tell the database
    MigrationHistory.delete().where(MigrationHistory.name == file).execute()


def lets_migrate(number=0, recurse=False):
    """Recursive Migration processing"""

    # If they passed a number that's the only one we want to run
    if number:
        number_file = glob(f"migrations/{number}*.py")[:1][0]
        run_migration(number_file)
        sys.exit()

    # Without a specific number we need to get the files we've already migrated
    history = MigrationHistory.select().dicts()

    # Get the next migration to run
    if history:
        if not recurse:
            rprint(
                "Last migration was: [i grey69]"
                + history[-1:][0]["name"]
                + "[/i grey69]"
            )
            print()
        last_number = history[-1:][0]["name"][:4]
        next_number = str(int(last_number) + 1).zfill(4)
        next_file = glob(f"migrations/{next_number}*.py")
        if next_file:
            run_migration(next_file[0])
            lets_migrate(recurse=True)
        else:
            print()
            rprint("  Migrations are complete :tada:")
    else:
        # Look for the first migration
        first_file = sorted(glob("migrations/*.py"))[:1][0]
        if first_file:
            run_migration(first_file)
            lets_migrate(recurse=True)
        else:
            print("No files found... nothing to do")


def run_migration(file):
    """Run the migration file"""

    # Change the file name into a python module name
    module_name = file.split("/")[0] + "." + file.split("/")[1][:-3]

    if not os.path.isfile(file):
        rprint(" [red]Unable to find migration file[/red]")
        rprint(f" {file} not found!")
        sys.exit()

    # Run the migration file
    print_str = "Running Migration: [sky_blue2]" + file + "[/sky_blue2]"
    rprint(print_str, end="")
    try:
        migration = import_module(module_name)
        migration.migrate()
        rprint(" [green]Successful[/green]")
    except Exception as exp:
        rprint(" [red]FAILED[/red]")
        rprint(f" Error was: [yellow1]{exp}[/yellow1]")
        print()
        sys.exit()

    # Let's tell the database
    MigrationHistory.create(name=file[11:-3])


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

from playhouse.migrate import MySQLMigrator
from playhouse.migrate import migrate as pw_migrate

# Model from the config file\n'''
    file_contents += (
        f"from {CONFIG['smalls']['model']} import {CONFIG['smalls']['object']}"
    )
    file_contents += '''

migrator = MySQLMigrator(db)

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
