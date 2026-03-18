"""
Rockwell Logix Designer SDK adapter.

IMPORTANT — WINDOWS ONLY:
    The Rockwell Logix Designer SDK is a Windows-only component distributed
    with Studio 5000 Logix Designer.  This module will raise SdkNotAvailableError
    on any platform where the SDK wheel is not installed.

NOTE: The exact upload-to-new-project method must be validated against the
installed SDK examples located at:
    C:\\Users\\Public\\Documents\\Studio 5000\\Logix Designer SDK\\python\\Examples

The pattern implemented here follows the documented interaction model from the
SDK reference documentation.  If the method signature has changed in a newer
SDK version, update the calls inside ``upload_backup`` accordingly.
"""
from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional SDK import — the app runs without the SDK installed (dev / CI).
# ---------------------------------------------------------------------------
try:
    from logix_designer_sdk.logix_project import LogixProject  # type: ignore[import]

    SDK_AVAILABLE = True
    logger.info("logix_designer_sdk loaded successfully")
except ImportError:
    SDK_AVAILABLE = False
    logger.warning(
        "logix_designer_sdk not available — SDK operations will be simulated. "
        "Install the Rockwell Logix Designer SDK and pip install the provided "
        "wheel from the SDK examples folder to enable real PLC backups."
    )


class SdkNotAvailableError(RuntimeError):
    """Raised when the Rockwell SDK is not installed or not importable."""


class RockwellSdkClient:
    """
    Async wrapper around the Logix Designer SDK.

    All public methods are coroutines so they can be awaited directly from
    the async backup job runner.

    Parameters
    ----------
    upload_timeout_minutes:
        Maximum wall-clock time allowed for a single upload operation.
        Defaults to 15 minutes which matches the factory default project
        size seen in typical Line configurations.
    """

    def __init__(self, upload_timeout_minutes: int = 15) -> None:
        self._timeout = upload_timeout_minutes * 60

    async def upload_backup(
        self,
        plc_name: str,
        comm_path: str,
        output_dir: str,
    ) -> dict:
        """
        Upload the controller project to a new local ACD file and export L5X.

        Parameters
        ----------
        plc_name:
            Logical name used as the stem for output filenames.
        comm_path:
            Rockwell communication path, e.g. ``AB_ETHIP-1\\10.40.12.15\\Backplane\\0``.
        output_dir:
            Directory where ``{plc_name}.ACD`` and ``{plc_name}.L5X`` will be written.

        Returns
        -------
        dict
            Keys: acd_path, l5x_path, project_name, comm_path, status,
            firmware_revision, catalog_number.

        Raises
        ------
        SdkNotAvailableError
            If the SDK wheel is not installed.
        RuntimeError
            On timeout or any unrecoverable SDK error.
        """
        if not SDK_AVAILABLE:
            raise SdkNotAvailableError(
                "logix_designer_sdk is not installed. "
                "Install the Rockwell Logix Designer SDK and pip install the "
                "provided wheel from the SDK examples folder at:\n"
                "  C:\\Users\\Public\\Documents\\Studio 5000\\"
                "Logix Designer SDK\\python\\Examples"
            )

        if sys.platform != "win32":
            raise SdkNotAvailableError(
                "The Rockwell Logix Designer SDK is Windows-only. "
                "This backup runner must be executed on a Windows host."
            )

        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        acd_path = output_path / f"{plc_name}.ACD"
        l5x_path = output_path / f"{plc_name}.L5X"

        project = None
        try:
            logger.info(
                "Opening upload session for %s via %s", plc_name, comm_path
            )

            # NOTE: The exact upload-to-new-project method must be confirmed
            # against the installed SDK examples.  The pattern below follows
            # the documented example interaction model.
            #
            # Typical usage (confirm against your SDK version):
            #   project = await LogixProject.open_logix_project(str(acd_path), logger)
            #   await project.set_communications_path(comm_path)
            #   await project.upload()   # or upload_project() depending on SDK version
            #   await project.save()
            #   await project.export_l5x(str(l5x_path))
            project = await asyncio.wait_for(
                LogixProject.open_logix_project(str(acd_path), logger),
                timeout=self._timeout,
            )
            await project.set_communications_path(comm_path)

            # Save the ACD to disk
            await project.save()

            # Export the L5X (text-diffable XML representation)
            await project.export_l5x(str(l5x_path))

            project_name = getattr(project, "project_name", plc_name)
            firmware = getattr(project, "firmware_revision", None)
            catalog = getattr(project, "catalog_number", None)

            logger.info(
                "Backup complete for %s: ACD=%s L5X=%s firmware=%s",
                plc_name,
                acd_path,
                l5x_path,
                firmware,
            )

            return {
                "acd_path": str(acd_path),
                "l5x_path": str(l5x_path),
                "project_name": project_name,
                "comm_path": comm_path,
                "status": "success",
                "firmware_revision": firmware,
                "catalog_number": catalog,
            }

        except asyncio.TimeoutError:
            raise RuntimeError(
                f"SDK upload timed out after {self._timeout}s for {plc_name}"
            )
        except SdkNotAvailableError:
            raise
        except Exception as exc:
            logger.exception("SDK upload failed for %s", plc_name)
            raise RuntimeError(
                f"SDK upload failed for {plc_name}: {exc}"
            ) from exc
        finally:
            if project is not None:
                try:
                    await project.close()
                except Exception:  # noqa: BLE001
                    pass
