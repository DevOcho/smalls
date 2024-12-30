# smalls
Python Peewee Database Aid - Migration / Rollback, Init, Seed, and Status

`smalls` is a utility that creates a process around Peewee's Playhouse.migrate
utility.  You can learn more here: [Peewee Migrate Docs](https://peewee.readthedocs.io/en/latest/peewee/playhouse.html#migrate).

## Installation

1) Copy the smalls.py file into your project and then create a config.ini with the following:

```
# config.ini
[smalls]
model=module.model
object=db
```

Where your `module.model` is the import path to your Peewee Model (or where ever
your database object is) and where your `object` is the Peewee database object.
We will do the following with what you put in there:

```python
from <model> import <object>
```
2) Create a table in your model

```python
class MigrationHistory(BaseModel):
    """Database Migration History"""

    id = AutoField(primary_key=True)
    name = CharField(unique=True)
    migrated_at = DateTimeField(null=False, default=datetime.now)
```

3) Create a `migrations` folder
4) If you want to use `smalls init` and `smalls seed` you will need to create `initdb.py` and `seed.py` files respectively.


## Usage

Smalls currently has 6 commands.  You can see those by running `smalls --help`.

```
Usage: smalls.py [OPTIONS] COMMAND [ARGS]...

  Peewee Database Manager

Options:
  -h, --help  Show this message and exit.

Commands:
  create    Create a new migration file
  init      Initialize the database
  migrate   Run migrations on the database
  rollback  Rollback migrations on the database
  seed      Load developer seed data into the database
  status    Status of the database migrations
```

Each individual command also has a help feature which you can access by running that command with `--help`.

For example, `smalls migrate --help`

### Create a new migration

Note: We expect smalls to be installed in the root folder of your project and we
also expect you to run it from that root folder.

Example,
```bash
./smalls.py create "adding the password_reset_count field to users"
```

This will create a file in the migrations folder with a sequential, zero padded number.

```bash
=======================================
| Smalls - Peewee Database Manager 👍 |
=======================================

Running at: 2024-12-30 09:40:17.359825
Creating a new file
 -- Created: migrations/0001_adding_the_password_reset_count_field_to_users.py
```

You can then edit that file to create your specific database changes.  We
include the Peewee migrate() documentation as an example script in the comment
at the top of new migration scripts so you can quickly reference how to make
changes.  For our above example, we would build code that looks like the
following:

```python
from peewee import IntegerField

def migrate():
    """Migration code goes here"""
    pw_migrate(
        migrator.add_column('users', 'reset_count', IntegerField(default=0)),
    )

def rollback():
    """Rollback code goes here"""
    pw_migrate(
        migrator.drop_column('users', 'reset_count'),
    )
```

Note: we've excluded the boiler-plate includes that `smalls` adds automatically to make your life better.

In every migration file we include the rollback function as well.  This let's
you keep the change and rollback code together.  This also allows you to
manage data in a production database in the same script.

### Run the migration

You can run your new migration script simply by running:

```bash
./smalls.py migrate
```

It will run the migration and report back to you success or failure.

```bash
=======================================
| Smalls - Peewee Database Manager 👍 |
=======================================

Running at: 2024-12-30 16:15:35.944041
Running Migration: migrations/0001_adding_the_password_reset_count_field_to_users.py Successful

  Migrations are complete 🎉
```

### Rollback the migration

This is pretty straight forward.  You need to give `smalls` the number of the
rollback you want to perform.

```bash
./smalls.py rollback 0123
```

If you want to rollback to the very beginning you can use 0000 as the number.

```bash
./smalls.py rollback 0000
```

### Initialize and seed a databse

At DevOcho we use `initdb.py` and `seed.py` for our database initialization and
data seeding, respectively.  Smalls has a convenience method for running those
if you wanted to include it in your process.

```bash
./smalls.py init
```

and

```bash
./smalls.py seed
```
