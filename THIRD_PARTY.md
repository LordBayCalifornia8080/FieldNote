# Third-party software

Fieldnotes source is MIT-licensed. Dependencies remain under their respective licenses. The dependency locks record exact versions and distribution hashes for this release; they are not a security certification or a full software bill of materials.

Direct runtime dependencies:

| Package | Upstream | License family |
| --- | --- | --- |
| FastAPI | https://github.com/fastapi/fastapi | MIT |
| Uvicorn | https://github.com/encode/uvicorn | BSD-3-Clause |
| SQLAlchemy | https://github.com/sqlalchemy/sqlalchemy | MIT |
| pydantic-settings | https://github.com/pydantic/pydantic-settings | MIT |
| argon2-cffi | https://github.com/hynek/argon2-cffi | MIT |
| markdown-it-py | https://github.com/executablebooks/markdown-it-py | MIT |

Development tools include pytest (MIT), HTTPX (BSD-3-Clause), Ruff (MIT), and jsdom (MIT). Transitive packages, Python, SQLite, and container operating-system components have additional notices and terms. Installed distributions and container images include their own license metadata; retain it when redistributing those components. The source ZIP does not vendor dependency code. All icons and CSS illustrations in `static/` are original project assets; there are no externally hosted fonts or images.
