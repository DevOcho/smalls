# smalls
Python Peewee Database Aid - Migration / Rollback, Init, Seed, and Status

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

```
from <model> import <object>
```

2) Create a `migrations` folder
3) If you want to use `smalls init` and `smalls seed` you will need to create `initdb.py` and `seed.py` files respectively.


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
