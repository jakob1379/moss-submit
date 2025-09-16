# moss_cli.py
from __future__ import annotations

import ipaddress
import os
import re
import socket
from dataclasses import dataclass
from glob import glob
from pathlib import Path
from typing import Annotated, Optional, Sequence, Tuple

import typer
from pydantic import BaseModel, Field, ValidationError, field_validator
from rich.console import Console
from rich.table import Table

app = typer.Typer(
    name="moss",
    help="""Submit code similarity jobs to Stanford MOSS.

To obtain a Moss account, send a mail message to moss@moss.stanford.edu with



subject: registeruser

body: mail username@domain """,
    no_args_is_help=True,
    add_completion=True,
)

console = Console()

DEFAULT_SERVER = "moss.stanford.edu"
DEFAULT_PORT = 7690
DEFAULT_LANGUAGE = "python"
DEFAULT_MAX_MATCHES = 10
DEFAULT_SHOW = 250

SUPPORTED_LANGUAGES = {
    "c",
    "cc",
    "java",
    "ml",
    "pascal",
    "ada",
    "lisp",
    "scheme",
    "haskell",
    "fortran",
    "ascii",
    "vhdl",
    "perl",
    "matlab",
    "python",
    "mips",
    "prolog",
    "spice",
    "vb",
    "csharp",
    "modula2",
    "a8086",
    "javascript",
    "plsql",
}

ENV_USER_ID = "MOSS_USER_ID"
ENV_SERVER = "MOSS_SERVER"
ENV_PORT = "MOSS_PORT"
ENV_LANGUAGE = "MOSS_LANGUAGE"
ENV_EXPERIMENTAL = "MOSS_EXPERIMENTAL"
ENV_MAX_MATCHES = "MOSS_MAX_MATCHES"
ENV_SHOW = "MOSS_SHOW"
ENV_DIRECTORY = "MOSS_DIRECTORY"
ENV_COMMENT = "MOSS_COMMENT"
ENV_BASE = "MOSS_BASE"
ENV_SKIP_LANG_CHECK = "MOSS_SKIP_LANGUAGE_CHECK"
ENV_DRY_RUN = "MOSS_DRY_RUN"
ENV_VERBOSE = 'MOSS_VERBOSE'

CONFIG_LOCATIONS = [
    Path("./.moss.toml"),
    Path.home() / ".config" / "moss" / "config.toml",
    Path.home() / ".moss.toml",
]


def is_text_file(path: Path, blocksize: int = 4096) -> bool:
    try:
        with path.open("rb") as f:
            chunk = f.read(blocksize)
        if b"\x00" in chunk:
            return False
        chunk.decode("utf-8", errors="replace")
        return True
    except Exception:
        return False


def expand_inputs(inputs: Sequence[str]) -> list[Path]:
    results: list[Path] = []
    for pattern in inputs:
        matches = [Path(p) for p in glob(pattern)]
        if matches:
            results.extend(matches)
        else:
            results.append(Path(pattern))
    seen: set[Path] = set()
    ordered: list[Path] = []
    for p in results:
        if p not in seen:
            seen.add(p)
            ordered.append(p)
    return ordered


class MossConfig(BaseModel):
    user_id: int = Field(..., description="MOSS user id (from signup email)")
    server: str = Field(DEFAULT_SERVER, description="MOSS server hostname")
    port: int = Field(DEFAULT_PORT, description="MOSS server TCP port")
    default_language: str = Field(DEFAULT_LANGUAGE, description="Default language")
    experimental: bool = Field(False, description="Use experimental server")

    @field_validator("user_id")
    @classmethod
    def validate_user_id(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("User ID must be positive")
        return v

    @field_validator("port")
    @classmethod
    def validate_port(cls, v: int) -> int:
        if not (1 <= v <= 65535):
            raise ValueError("Port must be 1-65535")
        return v

    @field_validator("server")
    @classmethod
    def validate_server(cls, v: str) -> str:
        v = v.strip()
        try:
            ipaddress.ip_address(v)
            return v
        except ValueError:
            if not re.match(r"^[A-Za-z0-9.-]+$", v):
                raise ValueError("Invalid server hostname")
            return v

    @field_validator("default_language")
    @classmethod
    def validate_lang(cls, v: str) -> str:
        return v.strip()


def load_toml(path: Path) -> dict:
    import tomllib

    with path.open("rb") as f:
        return tomllib.load(f)


def load_config() -> Optional[MossConfig]:
    data: dict = {}
    for loc in CONFIG_LOCATIONS:
        if loc.exists():
            try:
                data = load_toml(loc)
                break
            except Exception as e:
                console.print(f"[yellow]Warning: failed to parse {loc}: {e}[/]")
    if not data:
        return None

    moss = data.get("moss", data)
    try:
        return MossConfig(**moss)
    except ValidationError as e:
        console.print("[red]Invalid configuration[/]")
        console.print(e)
        return None


@dataclass
class MossOptions:
    language: str
    directory_mode: bool
    base_files: list[Path]
    max_matches: int
    comment: str
    show: int
    experimental: bool
    server: str
    port: int
    user_id: int
    files: list[Path]


class MossClientError(Exception):
    pass


class MossClient:
    def __init__(self, opts: MossOptions) -> None:
        self.opts = opts
        self.sock: socket.socket | None = None
        self._file_id_counter = 1

    def _connect(self) -> None:
        try:
            self.sock = socket.create_connection((self.opts.server, self.opts.port))
            self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except OSError as e:
            raise MossClientError(
                f"Could not connect to server {self.opts.server}:{self.opts.port} - {e}"
            ) from e

    def _send_line(self, line: str) -> None:
        assert self.sock is not None
        self.sock.sendall((line + "\n").encode("utf-8"))

    def _recv_line(self) -> str:
        assert self.sock is not None
        buf = bytearray()
        while True:
            ch = self.sock.recv(1)
            if not ch:
                break
            buf.extend(ch)
            if ch == b"\n":
                break
        return buf.decode("utf-8", errors="replace").rstrip("\n")

    def _upload_file(self, file: Path, file_id: int, lang: str) -> None:
        data = file.read_bytes()
        size = len(data)
        self._send_line(f"file {file_id} {lang} {size} {file.name}")
        assert self.sock is not None
        self.sock.sendall(data)

    def submit(self) -> str:
        self._connect()
        assert self.sock is not None

        self._send_line(f"moss {self.opts.user_id}")
        self._send_line(f"directory {1 if self.opts.directory_mode else 0}")
        self._send_line(f"X {1 if self.opts.experimental else 0}")
        self._send_line(f"maxmatches {self.opts.max_matches}")
        self._send_line(f"show {self.opts.show}")

        self._send_line(f"language {self.opts.language}")
        msg = self._recv_line()
        if msg.strip() == "no":
            self._send_line("end")
            raise MossClientError(f"Unrecognized language: {self.opts.language}")

        for bf in self.opts.base_files:
            console.print(f"[cyan]Uploading base:[/] {bf}")
            self._upload_file(bf, 0, self.opts.language)

        for f in self.opts.files:
            fid = self._file_id_counter
            self._file_id_counter += 1
            console.print(f"[cyan]Uploading:[/] {f}")
            self._upload_file(f, fid, self.opts.language)

        self._send_line(f"query 0 {self.opts.comment}")
        console.print("[green]Query submitted. Waiting for server response...[/]")
        result_url = self._recv_line().strip()
        self._send_line("end")

        try:
            self.sock.close()
        except Exception:
            pass
        return result_url


def validate_paths(
    base_files: Sequence[Path], files: Sequence[Path]
) -> Tuple[list[Path], list[Path]]:
    def check(paths: Sequence[Path], label: str) -> list[Path]:
        out: list[Path] = []
        for p in paths:
            if not p.exists():
                raise MossClientError(f"{label} '{p}' does not exist.")
            if not p.is_file():
                raise MossClientError(f"{label} '{p}' is not a file.")
            if not os.access(p, os.R_OK):
                raise MossClientError(f"{label} '{p}' is not readable.")
            if not is_text_file(p):
                raise MossClientError(f"{label} '{p}' is not a text file.")
            out.append(p.resolve())
        return out

    return check(base_files, "Base file"), check(files, "File")


def resolve_effective_config(
    user_id: int | None,
    language: str | None,
    server: str | None,
    port: int | None,
    experimental: bool | None,
) -> Tuple[int, str, str, int, bool]:
    cfg = load_config()

    eff_user = (
        user_id
        or (int(os.environ[ENV_USER_ID]) if ENV_USER_ID in os.environ else None)
        or (cfg.user_id if cfg else None)
    )
    if eff_user is None:
        raise MossClientError(
            "MOSS user id is required. Provide --user-id, or set "
            f"{ENV_USER_ID}, or define it in config."
        )

    eff_server = (
        server or os.environ.get(ENV_SERVER) or (cfg.server if cfg else DEFAULT_SERVER)
    )
    eff_port = (
        port
        or (int(os.environ[ENV_PORT]) if ENV_PORT in os.environ else None)
        or (cfg.port if cfg else DEFAULT_PORT)
    )
    eff_lang = (
        language
        or os.environ.get(ENV_LANGUAGE)
        or (cfg.default_language if cfg else DEFAULT_LANGUAGE)
    )
    eff_experimental = (
        experimental
        if experimental is not None
        else (os.environ.get(ENV_EXPERIMENTAL, "").lower() in {"1", "true", "t", "yes", "on"})
        or (cfg.experimental if cfg else False)
    )

    try:
        MossConfig(
            user_id=eff_user,
            server=eff_server,
            port=eff_port,
            default_language=eff_lang,
            experimental=eff_experimental,
        )
    except ValidationError as e:
        raise MossClientError(f"Invalid effective configuration: {e}") from e

    return eff_user, eff_lang, eff_server, eff_port, eff_experimental


FilesArg = Annotated[
    list[str],
    typer.Argument(
        ...,
        help="Files to submit. Globs allowed. Example: src/**/*.py",
        metavar="FILES...",
    ),
]

LanguageOpt = Annotated[
    Optional[str],
    typer.Option(
        "--language",
        "-l",
        help=f"Source language (default: {DEFAULT_LANGUAGE}).",
        envvar=ENV_LANGUAGE,
    ),
]

DirectoryOpt = Annotated[
    bool,
    typer.Option(
        "--directory",
        "-d",
        help="Treat submissions by directory rather than file.",
        envvar=ENV_DIRECTORY,
    ),
]

BaseOpt = Annotated[
    list[str],
    typer.Option(
        "--base",
        "-b",
        help="Base file (may be specified multiple times).",
        envvar=ENV_BASE,
    ),
]

MaxMatchesOpt = Annotated[
    int,
    typer.Option(
        "--max-matches",
        "-m",
        min=1,
        help="Ignore code appearing in more than N programs.",
        show_default=True,
        rich_help_panel="MOSS Options",
        envvar=ENV_MAX_MATCHES,
    ),
]

CommentOpt = Annotated[
    str,
    typer.Option(
        "--comment",
        "-c",
        help="Comment to attach to the report.",
        envvar=ENV_COMMENT,
    ),
]

ShowOpt = Annotated[
    int,
    typer.Option(
        "--show",
        "-n",
        min=1,
        help="Number of matching files to show in results.",
        envvar=ENV_SHOW,
    ),
]

ExperimentalOpt = Annotated[
    Optional[bool],
    typer.Option(
        "--experimental/--no-experimental",
        "-x",
        help="Use experimental server features.",
        envvar=ENV_EXPERIMENTAL,
    ),
]

UserIdOpt = Annotated[
    Optional[int],
    typer.Option(
        "--user-id",
        "-u",
        help=f"MOSS user id. Or set {ENV_USER_ID} / config.",
        envvar=ENV_USER_ID,
    ),
]

ServerOpt = Annotated[
    Optional[str],
    typer.Option(
        "--server",
        "-s",
        help=f"Override server hostname (default: {DEFAULT_SERVER}).",
        envvar=ENV_SERVER,
    ),
]

PortOpt = Annotated[
    Optional[int],
    typer.Option(
        "--port",
        "-p",
        help=f"Override server port (default: {DEFAULT_PORT}).",
        envvar=ENV_PORT,
    ),
]

SkipLangCheckOpt = Annotated[
    bool,
    typer.Option(
        "--skip-language-check",
        help="Skip local language name check (server still validates).",
        envvar=ENV_SKIP_LANG_CHECK,
    ),
]

DryRunOpt = Annotated[
    bool,
    typer.Option(
        "--dry-run",
        help="Validate inputs and show plan without contacting server.",
        envvar=ENV_DRY_RUN,
    ),
]

VerboseOpt = Annotated[
    bool,
    typer.Option(
        "--verbose",
        "-v",
        help="Verbose output.",
    ),
]


@app.command("submit")
def submit(
    files: FilesArg,
    language: LanguageOpt = None,
    directory: DirectoryOpt = False,
    base: BaseOpt = [],
    max_matches: MaxMatchesOpt = DEFAULT_MAX_MATCHES,
    comment: CommentOpt = "",
    show: ShowOpt = DEFAULT_SHOW,
    experimental: ExperimentalOpt = None,
    user_id: UserIdOpt = None,
    server: ServerOpt = None,
    port: PortOpt = None,
    skip_lang_check: SkipLangCheckOpt = False,
    dry_run: DryRunOpt = False,
    verbose: VerboseOpt = False,
) -> None:
    """
    Submit a MOSS query.

    Example:
      moss submit -l python -b skeleton.py src/**/*.py
    """
    try:
        eff_user, eff_lang, eff_server, eff_port, eff_exp = resolve_effective_config(
            user_id=user_id,
            language=language,
            server=server,
            port=port,
            experimental=experimental,
        )

        if not skip_lang_check and eff_lang not in SUPPORTED_LANGUAGES:
            console.print(
                f"[yellow]Warning: language '{eff_lang}' not in local known list; "
                "server will validate.[/]"
            )

        base_files = expand_inputs(base)
        data_files = expand_inputs(files)
        if not data_files:
            raise MossClientError("No input files resolved.")

        base_files_res, data_files_res = validate_paths(base_files, data_files)

        if verbose or dry_run:
            tbl = Table(title="MOSS submission plan")
            tbl.add_column("Field", style="bold cyan")
            tbl.add_column("Value")
            tbl.add_row("Server", f"{eff_server}:{eff_port}")
            tbl.add_row("User ID", str(eff_user))
            tbl.add_row("Language", eff_lang)
            tbl.add_row("Directory mode", str(directory))
            tbl.add_row("Max matches (-m)", str(max_matches))
            tbl.add_row("Show (-n)", str(show))
            tbl.add_row("Experimental (-x)", str(eff_exp))
            tbl.add_row("Comment (-c)", comment or "(none)")
            if base_files_res:
                tbl.add_row("Base files", "\n".join(str(p) for p in base_files_res))
            tbl.add_row("Files", "\n".join(str(p) for p in data_files_res))
            console.print(tbl)

        if dry_run:
            console.print("[green]Dry run: no network calls made.[/]")
            raise typer.Exit(code=0)

        opts = MossOptions(
            language=eff_lang,
            directory_mode=directory,
            base_files=base_files_res,
            max_matches=max_matches,
            comment=comment,
            show=show,
            experimental=eff_exp,
            server=eff_server,
            port=eff_port,
            user_id=eff_user,
            files=data_files_res,
        )
        client = MossClient(opts)
        result_url = client.submit()
        console.print(f"[bold green]Result:[/] {result_url}")

    except MossClientError as e:
        console.print(f"[red]Error:[/] {e}")
        raise typer.Exit(code=2)
    except Exception as e:
        console.print(f"[red]Unexpected error:[/] {e}")
        raise typer.Exit(code=1)


@app.command("env")
def show_env() -> None:
    """
    Show relevant environment variables if set.
    """

    def val(name: str) -> str:
        return os.environ.get(name, "(not set)")

    tbl = Table(title="MOSS environment variables")
    tbl.add_column("Variable", style="bold")
    tbl.add_column("Value")
    tbl.add_row(ENV_USER_ID, val(ENV_USER_ID))
    tbl.add_row(ENV_SERVER, val(ENV_SERVER))
    tbl.add_row(ENV_PORT, val(ENV_PORT))
    tbl.add_row(ENV_LANGUAGE, val(ENV_LANGUAGE))
    tbl.add_row(ENV_EXPERIMENTAL, val(ENV_EXPERIMENTAL))
    tbl.add_row(ENV_MAX_MATCHES, val(ENV_MAX_MATCHES))
    tbl.add_row(ENV_SHOW, val(ENV_SHOW))
    tbl.add_row(ENV_DIRECTORY, val(ENV_DIRECTORY))
    tbl.add_row(ENV_COMMENT, val(ENV_COMMENT))
    tbl.add_row(ENV_BASE, val(ENV_BASE))
    tbl.add_row(ENV_SKIP_LANG_CHECK, val(ENV_SKIP_LANG_CHECK))
    tbl.add_row(ENV_VERBOSE, val(ENV_VERBOSE))
    tbl.add_row(ENV_DRY_RUN, val(ENV_DRY_RUN))
    console.print(tbl)


@app.command("config")
def where_config() -> None:
    """
    Show searched config locations and whether they exist.
    """
    tbl = Table(title="MOSS config search paths")
    tbl.add_column("Path")
    tbl.add_column("Exists")
    for p in CONFIG_LOCATIONS:
        tbl.add_row(str(p), "yes" if p.exists() else "no")
    console.print(tbl)
