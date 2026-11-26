<p align="center">
  <img src=".github/assets/moss-session.svg" width="100%" alt="Animated diagram of a moss submit session: skeleton.py (base code), alice.py and bob.py are uploaded to moss.stanford.edu:7690 one protocol line at a time, the server replies with a report URL, and the report pairs alice.py with bob.py and highlights their matching code.">
</p>

# moss-submit

A command-line client for [MOSS](https://theory.stanford.edu/~aiken/moss/), Stanford's
code similarity service. Point it at a set of source files, and it uploads them and prints
the URL of the MOSS report.

```console
$ moss submit -l python -b skeleton.py submissions/*.py
Uploading base: /home/you/course/skeleton.py
Uploading: /home/you/course/submissions/alice.py
Uploading: /home/you/course/submissions/bob.py
Query submitted. Waiting for server response...
Result: http://moss.stanford.edu/results/…
```

Before connecting, it checks that every file exists, is readable and is text, so a stray
binary or a typo in a path fails locally instead of halfway through an upload.

## Before you start

You need Python 3.13 or newer and a MOSS user id. To get a user id, send an email to
`moss@moss.stanford.edu` whose body is exactly:

```text
registeruser
mail username@domain
```

with your own address in place of `username@domain`. The reply contains your numeric user id.

## Install

With [uv](https://docs.astral.sh/uv/):

```sh
uv tool install git+https://github.com/jakob1379/moss-submit
```

Or with pipx:

```sh
pipx install git+https://github.com/jakob1379/moss-submit
```

Both put a `moss` command on your `PATH`. To run from a checkout instead:

```sh
git clone https://github.com/jakob1379/moss-submit
cd moss-submit
uv run moss --help
```

## Usage

Store your user id once, then submit:

```sh
export MOSS_USER_ID=123456
moss submit -l java -b Starter.java "submissions/*.java"
```

Base files (`-b`) hold code you handed out, such as a skeleton or starter template.
MOSS does not report matches against code that appears in a base file.

Patterns are expanded by `moss` itself when you quote them, or by your shell when you
don't. `moss` uses non-recursive globbing, so `**` matches a single directory level.

Check what would be sent without contacting the server:

```sh
moss submit --dry-run -b skeleton.py "submissions/*.py"
```

`--dry-run` and `--verbose` print the submission plan: server, user id, language, MOSS
options and the resolved file list.

### Commands

| Command       | What it does                                            |
| ------------- | ------------------------------------------------------- |
| `moss submit` | Upload files and print the report URL                   |
| `moss env`    | Show which `MOSS_*` environment variables are set       |
| `moss config` | Show the config file locations and whether each exists  |

### `moss submit` options

Options other than `--verbose` can also be set through an environment variable.

| Option                          | Environment variable       | Default             | Meaning                                                  |
| ------------------------------- | -------------------------- | ------------------- | -------------------------------------------------------- |
| `-u`, `--user-id`               | `MOSS_USER_ID`             |                     | Your MOSS user id (required here or in the config file)  |
| `-l`, `--language`              | `MOSS_LANGUAGE`            | `python`            | Source language                                          |
| `-b`, `--base`                  | `MOSS_BASE`                |                     | Base file; repeat for several                            |
| `-d`, `--directory`             | `MOSS_DIRECTORY`           | off                 | Treat submissions by directory rather than by file       |
| `-m`, `--max-matches`           | `MOSS_MAX_MATCHES`         | `10`                | Ignore code that appears in more than N programs         |
| `-n`, `--show`                  | `MOSS_SHOW`                | `250`               | Number of matching files to show in the results          |
| `-c`, `--comment`               | `MOSS_COMMENT`             |                     | Comment attached to the report                           |
| `-x`, `--experimental`          | `MOSS_EXPERIMENTAL`        | off                 | Use the experimental server                              |
| `-s`, `--server`                | `MOSS_SERVER`              | `moss.stanford.edu` | Server hostname                                          |
| `-p`, `--port`                  | `MOSS_PORT`                | `7690`              | Server port                                              |
| `--skip-language-check`         | `MOSS_SKIP_LANGUAGE_CHECK` | off                 | Skip the local language name check; the server still checks |
| `--dry-run`                     | `MOSS_DRY_RUN`             | off                 | Validate inputs and show the plan without connecting     |
| `-v`, `--verbose`               |                            | off                 | Print the submission plan before uploading               |

<details>
<summary>Languages known to the local check</summary>

`a8086`, `ada`, `ascii`, `c`, `cc`, `csharp`, `fortran`, `haskell`, `java`, `javascript`,
`lisp`, `matlab`, `mips`, `ml`, `modula2`, `pascal`, `perl`, `plsql`, `prolog`, `python`,
`scheme`, `spice`, `vb`, `vhdl`

Any other name prints a warning and is passed on; the server rejects languages it does not
recognise.

</details>

## Configuration file

Instead of flags or environment variables, you can keep settings in a TOML file. `moss`
reads the first one it finds:

1. `./.moss.toml`
2. `~/.config/moss/config.toml`
3. `~/.moss.toml`

```toml
[moss]
user_id = 123456
default_language = "java"
server = "moss.stanford.edu"
port = 7690
experimental = false
```

Only `user_id` is required. The keys can also sit at the top level, without the `[moss]`
table. Command-line flags and environment variables take precedence over the file.

## Credits

MOSS is developed and hosted by Alex Aiken at Stanford University. This project is an
independent client for it.
