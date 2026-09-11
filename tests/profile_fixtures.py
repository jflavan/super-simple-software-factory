"""Fixture repositories, built in tmp_path.

Every test that exercises detection builds the tree it needs here rather than
pointing at a real repository. A fixture is the only place in this test suite
allowed to use concrete names like `apps/web` — they are this fake repo's
layout, not a profile's.
"""

from __future__ import annotations

import json
from pathlib import Path

CSPROJ_APP = """<Project Sdk="Microsoft.NET.Sdk.Web">
  <PropertyGroup><TargetFramework>net10.0</TargetFramework></PropertyGroup>
</Project>
"""

CSPROJ_UNIT = """<Project Sdk="Microsoft.NET.Sdk">
  <ItemGroup>
    <PackageReference Include="Microsoft.NET.Test.Sdk" Version="17.11.0" />
    <PackageReference Include="xunit" Version="2.9.0" />
  </ItemGroup>
</Project>
"""

CSPROJ_INTEGRATION = """<Project Sdk="Microsoft.NET.Sdk">
  <ItemGroup>
    <PackageReference Include="Microsoft.NET.Test.Sdk" Version="17.11.0" />
    <PackageReference Include="xunit" Version="2.9.0" />
    <PackageReference Include="Testcontainers.PostgreSql" Version="3.10.0" />
  </ItemGroup>
</Project>
"""

JUSTFILE = """set shell := ["bash", "-c"]

api_dir := "apps/api"

default:
    @just --list

# run the fast suite
test-unit: build-sln
    dotnet test

build-sln:
    dotnet build

check-web dir="apps/web":
    npm --prefix {{dir}} run check
"""


def write(root: Path, relative: str, text: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def sln(root: Path, name: str, project_paths: list[str], folders: list[str] = ()) -> Path:
    """A minimal but real .sln naming the given projects (repo-relative)."""
    lines = ["Microsoft Visual Studio Solution File, Format Version 12.00"]
    for index, project in enumerate(project_paths):
        stem = Path(project).stem
        windows_path = project.replace("/", "\\")
        lines.append(
            f'Project("{{9A19103F-16F7-4668-BE54-9A1E7A4F7556}}") = "{stem}", '
            f'"{windows_path}", "{{0000000{index}-0000-0000-0000-000000000000}}"')
        lines.append("EndProject")
    for index, folder in enumerate(folders):
        lines.append(
            f'Project("{{2150E333-8FDC-42A3-9474-1A3956D46DE8}}") = "{folder}", '
            f'"{folder}", "{{FFFFFFF{index}-0000-0000-0000-000000000000}}"')
        lines.append("EndProject")
    return write(root, name, "\n".join(lines) + "\n")


def package(root: Path, directory: str, scripts: dict[str, str],
            marker: str = "@sveltejs/kit", lockfile: str = "package-lock.json") -> Path:
    """A package.json declaring `marker` as a dependency, plus its lockfile."""
    manifest = {"name": Path(directory).name, "scripts": scripts,
                "devDependencies": {marker: "^2.20.0"} if marker else {}}
    path = write(root, f"{directory}/package.json", json.dumps(manifest, indent=2))
    write(root, f"{directory}/{lockfile}", "{}")
    return path


def dotnet_svelte_repo(root: Path, *, integration: bool = True,
                       frontends: list[str] = ("apps/web",),
                       justfile_text: str = "") -> Path:
    """The default fixture: one app, one unit-test project, optional integration."""
    projects = ["apps/api/Api/Api.csproj", "apps/api/Api.Tests/Api.Tests.csproj"]
    write(root, "apps/api/Api/Api.csproj", CSPROJ_APP)
    write(root, "apps/api/Api.Tests/Api.Tests.csproj", CSPROJ_UNIT)
    if integration:
        projects.append("apps/api/Api.IntegrationTests/Api.IntegrationTests.csproj")
        write(root, "apps/api/Api.IntegrationTests/Api.IntegrationTests.csproj",
              CSPROJ_INTEGRATION)
    sln(root, "Fixture.sln", projects)
    for directory in frontends:
        package(root, directory, {"check": "svelte-check", "test": "vitest run",
                                  "build": "vite build"})
    if justfile_text:
        write(root, "justfile", justfile_text)
    return root
