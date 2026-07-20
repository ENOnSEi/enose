"""Reconcile the DB schema with Alembic's migration state on every startup.

Switching git branches or checking out an older commit can leave the DB
ahead of, or behind, the migration files present on disk (a later
migration file simply doesn't exist yet in an older commit's tree, or the
DB was migrated forward under a different branch). Rather than surfacing
that later as an opaque "column does not exist" error the first time a
query touches the changed table, check the DB's stamped revision against
what the currently checked-out code knows about and run `upgrade` or
`downgrade` automatically when it's safe to do so.
"""

import asyncio
import logging
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy.ext.asyncio import AsyncEngine

logger = logging.getLogger("app.migrations")

_API_DIR = Path(__file__).resolve().parents[2]  # api/


def _alembic_config() -> Config:
    cfg = Config(str(_API_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(_API_DIR / "migrations"))
    return cfg


def _is_ancestor(script: ScriptDirectory, ancestor: str | None, descendant: str) -> bool:
    """True if ``ancestor`` is reached by walking down_revision from ``descendant``."""
    if ancestor is None:
        return True
    return any(rev.revision == ancestor for rev in script.iterate_revisions(descendant, None))


async def sync_schema_with_alembic(engine: AsyncEngine) -> None:
    try:
        cfg = _alembic_config()
        script = ScriptDirectory.from_config(cfg)
        head = script.get_current_head()

        async with engine.connect() as conn:
            heads = await conn.run_sync(
                lambda sync_conn: MigrationContext.configure(sync_conn).get_current_heads()
            )
        db_revision = heads[0] if heads else None

        if db_revision == head:
            logger.info("[alembic] esquema al día (%s)", head)
            return

        if db_revision is None:
            # Sin alembic_version todavía. create_db_and_tables() ya habrá
            # creado cualquier tabla que faltase con la forma *actual* de
            # los modelos, así que si aplicar las migraciones desde cero
            # falla (columnas que ya existen), asumimos que el esquema ya
            # coincide con head y simplemente lo marcamos como tal.
            try:
                await asyncio.to_thread(command.upgrade, cfg, "head")
                logger.info("[alembic] migraciones aplicadas desde cero hasta %s", head)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "[alembic] no se pudieron aplicar migraciones desde cero (%s); "
                    "se asume que el esquema ya coincide con head y se marca (stamp).",
                    exc,
                )
                await asyncio.to_thread(command.stamp, cfg, "head")
            return

        known = {rev.revision for rev in script.walk_revisions()}
        if db_revision not in known:
            logger.warning(
                "[alembic] la revisión de la BD (%s) no está entre los ficheros de "
                "migración de esta rama/commit — se omite la sincronización "
                "automática. Cambia a la rama que la contiene, o ejecuta "
                "`alembic upgrade`/`downgrade` manualmente.",
                db_revision,
            )
            return

        if _is_ancestor(script, db_revision, head):
            logger.info("[alembic] actualizando %s -> %s", db_revision, head)
            await asyncio.to_thread(command.upgrade, cfg, "head")
        elif _is_ancestor(script, head, db_revision):
            logger.info("[alembic] revirtiendo %s -> %s", db_revision, head)
            await asyncio.to_thread(command.downgrade, cfg, head)
        else:
            logger.warning(
                "[alembic] la revisión de la BD (%s) y el head del código (%s) "
                "están en ramas de migración divergentes — se omite la "
                "sincronización automática.",
                db_revision,
                head,
            )
    except Exception:  # noqa: BLE001
        logger.exception("[alembic] fallo comprobando/sincronizando el esquema; continúa el arranque")
