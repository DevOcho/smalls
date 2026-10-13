# smalls

Smalls is a single-file command line tool that runs numbered database migrations
for [Peewee](https://docs.peewee-orm.com/) projects: create, migrate, rollback,
status, init and seed.  It is a thin process around Peewee's
[playhouse.migrate](https://docs.peewee-orm.com/en/latest/peewee/playhouse.html#migrate).

| I want to... | Go to |
|--------------|-------|
| Use smalls in my project | [Quick start](#quick-start) |
| See every setting and environment variable | [Configuration](#configuration) |
| Learn what each command does | [Commands](#commands) |
| Change smalls itself | [Working on smalls](#working-on-smalls) |

## Quick start

1. Install the dependencies in your project:

   ```bash
   pip install peewee click rich
   ```

   You also need the driver for your database (for example `psycopg2` for
   PostgreSQL or `pymysql` for MySQL).  Smalls does not install it for you.

2. Copy `smalls.py` into the root folder of your project and make it executable:

   ```bash
   chmod +x smalls.py
   ```

3. Create a `config.ini` next to it:

   ```ini
   [smalls]
   model=module.model
   object=db
   ```

   `model` is the import path of the module that holds your Peewee database
   object, and `object` is the name of that object.  Smalls does the equivalent
   of `from module.model import db`.

4. Create the migrations folder and your first migration:

   ```bash
   mkdir migrations
   ./smalls.py create "adding the password_reset_count field to users"
   ```

5. Edit the new file in `migrations/`, then run it:

   ```bash
   ./smalls.py migrate
   ```

Always run smalls from the root folder of your project.  It looks for
`config.ini`, `migrations/` and your model relative to that folder.

## Requirements

| Requirement | Version |
|-------------|---------|
| Python | 3.10 or newer |
| peewee | 3.17 or newer (3.x) |
| click | 8.3 or newer |
| rich | 14.2 or newer |
| Database driver | Whatever your Peewee database needs |

Exact pinned versions are in `requirements.txt`.

## Configuration

Every setting can come from an environment variable or from the `[smalls]`
section of `config.ini`.  The order is always:

1. Environment variable, if it is set and not empty
2. `config.ini`
3. The default

### Settings

| Environment variable | `config.ini` key | Default | Used by | What it is |
|----------------------|------------------|---------|---------|------------|
| `SMALLS_MODEL` | `model` | none, **required** | every command | Import path of the module with your database object |
| `SMALLS_OBJECT` | `object` | `db` | every command | Name of the Peewee database object in that module |
| `SMALLS_VERSION` | `smalls_version` | `0.0.0` | `magic`, and stamped on every migration | Version of the code being deployed, such as `1.9.4` |
| `SMALLS_INIT_SCRIPT` | `init_script` | `initdb.py` | `init` | Script that initializes the database |
| `SMALLS_SEED_SCRIPT` | `seed_script` | `seed.py` | `seed` | Script that loads seed data |

### Environment-only variables

| Environment variable | Default | Used by | What it is |
|----------------------|---------|---------|------------|
| `SMALLS_CONFIG` | `config.ini` | every command | Path to the config file |
| `SMALLS_ALLOW_AUTO_ROLLBACK` | off | `magic` | Lets `magic` roll the schema back.  On with `1`, `true`, `yes` or `on` |

Only `model` is required.  If it is missing, smalls stops with an error before
running any command.

### Examples

A full `config.ini`:

```ini
[smalls]
model=app.database
object=db
smalls_version=1.9.4
init_script=scripts/initdb.py
seed_script=scripts/seed.py
```

Use a different config file for production:

```bash
SMALLS_CONFIG="/path/to/production.config.ini" ./smalls.py migrate
```

Run without any `config.ini`, for example in CI:

```bash
SMALLS_MODEL="app.database" SMALLS_OBJECT="db" ./smalls.py status
```

Let the deployed image version drive the migrations:

```bash
SMALLS_VERSION="1.9.4" ./smalls.py magic
```

## Commands

Run `./smalls.py --help` to list them, and `./smalls.py <command> --help` for
the details of one.

| Command | What it does |
|---------|--------------|
| `create "description"` | Creates the next numbered migration file |
| `migrate` | Runs every migration that has not been applied yet |
| `migrate -n 0002` | Runs only that migration |
| `status` | Shows the current migration and the ones still to run |
| `rollback 0001` | Rolls back every migration after that number |
| `magic` | Migrates or rolls back based on `SMALLS_VERSION` |
| `init` | Runs your init script |
| `seed` | Runs your seed script |

### Create a new migration

```bash
./smalls.py create "adding the password_reset_count field to users"
```

This creates a file in the migrations folder with a sequential, zero padded number.

```
=======================================
| Smalls - Peewee Database Manager 👍 |
=======================================

Running at: 2024-12-30 09:40:17.359825
Creating a new file
 -- Created: migrations/0001_adding_the_password_reset_count_field_to_users.py
```

The new file imports your database object, builds a `migrator` for it (smalls
picks the right one for PostgreSQL, MySQL or SQLite) and includes the Peewee
migrate examples in a comment at the top.  You fill in two functions:

```python3
from peewee import IntegerField


def migrate():
    """Migration code goes here"""
    pw_migrate(
        migrator.add_column("users", "reset_count", IntegerField(default=0)),
    )


def rollback():
    """Rollback code goes here"""
    pw_migrate(
        migrator.drop_column("users", "reset_count"),
    )
```

Note: we've excluded the boiler-plate includes that `smalls.py` adds automatically.

Keeping the change and its rollback in the same file also lets you manage data
in a production database in the same script.

### Run the migrations

```bash
./smalls.py migrate
```

```
=======================================
| Smalls - Peewee Database Manager 👍 |
=======================================

Running at: 2024-12-30 16:15:35.944041
Running Migration: migrations/0001_adding_the_password_reset_count_field_to_users.py Successful

  Migrations are complete 🎉
```

Smalls continues from the highest numbered migration it has applied and runs
the next numbers in order.

To run a single migration, pass its 4 digit number:

```bash
./smalls.py migrate -n 0002
```

### Rollback

Give `smalls.py` the 4 digit number you want to roll back **to**.  It asks for
confirmation first, and answering no stops it.

```bash
./smalls.py rollback 0123
```

The migration with the number you give is NOT rolled back.  To undo it you need
to go one lower.  To roll back everything, use `0000`:

```bash
./smalls.py rollback 0000
```

You can think of it like this:

```text
0000 Initial database
0001 Your update
0002 Some future update
```

Rolling back to 0001 rolls back "to" your change but does not run its
`rollback()`.

### Magic

`magic` is meant for deploys.  It compares `SMALLS_VERSION` with the version
stamped on the last migration that ran, and decides what to do:

| `SMALLS_VERSION` compared to the database | What `magic` does |
|-------------------------------------------|-------------------|
| No migrations applied yet | Runs all migrations |
| Higher | Runs the pending migrations |
| Same | Runs any migration files that have not been applied yet |
| Lower | Stops with an error, unless `SMALLS_ALLOW_AUTO_ROLLBACK` is on |

Versions are compared as numbers, so `1.10.0` is higher than `1.9.0`.

With `SMALLS_ALLOW_AUTO_ROLLBACK` on and a lower version, `magic` rolls back to
the last migration stamped with that version.  It refuses if no migration
carries that version, or if `SMALLS_VERSION` was not set at all.

```bash
SMALLS_VERSION="1.8.0" SMALLS_ALLOW_AUTO_ROLLBACK="true" ./smalls.py magic
```

### Initialize and seed a database

At DevOcho we use `initdb.py` and `seed.py` for database initialization and data
seeding.  Since every project is so different, smalls assumes those scripts know
what to do and just runs them with the same Python interpreter.

```bash
./smalls.py init
./smalls.py seed
```

If the script does not exist, smalls says so and does nothing.  If the script
fails, smalls exits with the same exit code.

## Safety rules

These hold in every environment:

- **A failed migration or rollback stops the run** with a non-zero exit code and
  is not recorded as applied.  Fix it and run again.
- **Duplicate numbers stop the run.**  Two files with the same 4 digit number
  usually come from merging two branches.  Renumber the one that has not been
  applied yet.
- **Gaps stop the run.**  If `0004` and `0006` exist but `0005` does not,
  smalls refuses to continue.
- **Skipped files are reported.**  If a file numbered below the last applied
  migration never ran, smalls lists it when it finishes.  Run it with
  `migrate -n`.
- **`magic` never rolls back on its own** unless `SMALLS_ALLOW_AUTO_ROLLBACK` is on.

## The migration history table

Smalls connects to your database when it starts, for every command including
`--help`.  On the first run it creates a `migration_history` table to track what
it has applied:

```python3
class MigrationHistory(Model):
    """Database Migration History"""

    id = AutoField(primary_key=True)
    name = CharField(unique=True)
    migrated_at = DateTimeField(null=False, default=datetime.now)
    version = CharField(null=False, max_length=32)
```

### Upgrading from an older smalls

- `version` used to be an integer column.  Smalls does not alter an existing
  table, so change that column to a 32 character string yourself before running
  this version.
- `SMALLS_ENV` is no longer used.  Failed migrations are fatal everywhere.
- `magic` no longer rolls back by default.  Set `SMALLS_ALLOW_AUTO_ROLLBACK` if
  your deploys relied on that.
- New migration files use `SchemaMigrator.from_database()` instead of a fixed
  MySQL migrator.  Existing migration files keep working as they are.

## Working on smalls

All of the code is in `smalls.py`.  There is no package to build: projects use
smalls by copying that one file.

### Set up

You need [Poetry](https://python-poetry.org/) 2.x.

```bash
poetry install
poetry run pre-commit install
```

`poetry install` gives you the runtime dependencies plus `pre-commit` and
`pylint`.

### Check your changes

```bash
poetry run pre-commit run --all-files
```

This runs black, isort, flake8 (max line length 110) and pylint, the same hooks
that run on every commit.

There is no automated test suite yet.  Try your change against a throwaway
SQLite project before opening a pull request:

```bash
mkdir -p /tmp/smalls-sandbox/migrations && cd /tmp/smalls-sandbox
printf 'from peewee import SqliteDatabase\ndb = SqliteDatabase("test.db")\n' > model.py
printf '[smalls]\nmodel=model\nobject=db\nsmalls_version=1.0.0\n' > config.ini

PYTHONPATH=. python /path/to/smalls/smalls.py create "first"
PYTHONPATH=. python /path/to/smalls/smalls.py migrate
PYTHONPATH=. python /path/to/smalls/smalls.py status
```

### Where things are in `smalls.py`

| Section | What is there |
|---------|---------------|
| Top of the file | Settings (`_get_setting`), the `MigrationHistory` model, table creation |
| `@cli.command()` functions | One per command: `migrate`, `create`, `rollback`, `status`, `init`, `seed`, `magic` |
| `# Utilities` | The work behind the commands: `lets_migrate`, `run_migration`, `run_rollback`, `magic_rollback`, directory validation |
| `create_migration_file` | The template written by `create` |

### Changing dependencies

`pyproject.toml` is the source of truth.  `poetry.lock` and `requirements.txt`
are generated from it, so do not edit them by hand:

```bash
poetry add <package>
poetry export -f requirements.txt --output requirements.txt
```

`poetry export` needs the
[export plugin](https://github.com/python-poetry/poetry-plugin-export).

### Things to keep true

- Find "the last migration" with `latest_migration()`, never with an unordered
  query.
- Exit with a non-zero code on every failure, so deploy pipelines notice.
- Do not hardcode project paths or database types.  Add a setting instead, and
  document it in the [Configuration](#configuration) tables.
