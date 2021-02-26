# Copyright (C) 2021 Canonical Ltd
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""LXC wrapper."""
import logging
import pathlib
import shlex
import shutil
import subprocess
from typing import Any, Dict, List, Optional

import yaml

from .errors import LXDError
from .yaml_loader import _load_yaml

logger = logging.getLogger(__name__)


class LXC:  # pylint: disable=too-many-public-methods
    """Wrapper for lxc."""

    def __init__(
        self,
        *,
        lxc_path: Optional[pathlib.Path] = None,
    ):
        if lxc_path is None:
            self.lxc_path: pathlib.Path = pathlib.Path("lxc")
        else:
            self.lxc_path = lxc_path

    def _run(  # pylint: disable=redefined-builtin
        self,
        command: List[str],
        *,
        check: bool = True,
        project: str = "default",
        **kwargs,
    ) -> subprocess.CompletedProcess:
        """Execute command in instance_name, allowing output to console."""
        command = [str(self.lxc_path), "--project", project, *command]

        logger.warning("Executing on host: %s", shlex.join(command))
        return subprocess.run(command, check=check, **kwargs)

    def config_device_add_disk(
        self,
        *,
        instance_name: str,
        source: pathlib.Path,
        destination: pathlib.Path,
        device_name: Optional[str] = None,
        project: str = "default",
        remote: str = "local",
    ) -> None:
        """Mount host source directory to target mount point."""
        if device_name is None:
            device_name = destination.as_posix().replace("/", "_")

        command = [
            "config",
            "device",
            "add",
            f"{remote}:{instance_name}",
            device_name,
            "disk",
            f"source={source.as_posix()}",
            f"path={destination.as_posix()}",
        ]

        try:
            self._run(
                command,
                capture_output=True,
                check=True,
                project=project,
            )
        except subprocess.CalledProcessError as error:
            raise LXDError.from_called_process_error(
                brief=f"Failed to add disk to instance {instance_name!r}.",
                error=error,
            )

    def config_device_show(
        self, *, instance_name: str, project: str = "default", remote: str = "local"
    ) -> Dict[str, Any]:
        """Show device config."""
        command = ["config", "device", "show", f"{remote}:{instance_name}"]

        try:
            proc = self._run(
                command,
                capture_output=True,
                check=True,
                project=project,
            )
        except subprocess.CalledProcessError as error:
            raise LXDError.from_called_process_error(
                brief=f"Failed to list devices for {instance_name!r}.",
                error=error,
            )

        return _load_yaml(proc.stdout)

    def config_set(
        self,
        *,
        instance_name: str,
        key: str,
        value: str,
        project: str = "default",
        remote: str = "local",
    ) -> None:
        """Set instance_name configuration key."""
        command = ["config", "set", f"{remote}:{instance_name}", key, value]

        try:
            self._run(
                command,
                capture_output=True,
                check=True,
                project=project,
            )
        except subprocess.CalledProcessError as error:
            raise LXDError.from_called_process_error(
                brief=f"Failed to set config key for instance {instance_name!r}.",
                error=error,
            )

    def delete(
        self,
        *,
        instance_name: str,
        project: str = "default",
        remote: str = "local",
        force=False,
    ) -> None:
        """Delete instance_name."""
        command = ["delete", f"{remote}:{instance_name}"]

        if force:
            command.append("--force")

        try:
            self._run(
                command,
                capture_output=True,
                check=True,
                project=project,
            )
        except subprocess.CalledProcessError as error:
            raise LXDError.from_called_process_error(
                brief=f"Failed to delete instance {instance_name!r}.",
                error=error,
            )

    def _formulate_command(
        self,
        *,
        command: List[str],
        instance_name: str,
        cwd: str = "/root",
        mode: str = "auto",
        project: str = "default",
        remote: str = "local",
        env: Optional[Dict[str, str]] = None,
    ) -> List[str]:
        """Formulate command to run."""
        final_cmd = [
            str(self.lxc_path),
            "--project",
            project,
            "exec",
            f"{remote}:{instance_name}",
        ]

        if cwd != "/root":
            final_cmd.extend(["--cwd", cwd])

        if mode != "auto":
            final_cmd.extend(["--mode", mode])

        final_cmd.append("--")

        if env is not None:
            env_args = [f"{k}={v}" for k, v in env.items()]
            final_cmd.extend(["env", *env_args])

        final_cmd.extend(command)
        return final_cmd

    def exec(
        self,
        *,
        command: List[str],
        instance_name: str,
        cwd: str = "/root",
        mode: str = "auto",
        project: str = "default",
        remote: str = "local",
        runner=subprocess.run,
        **kwargs,
    ):
        """Execute command in instance_name with specified runner."""
        command = self._formulate_command(
            command=command,
            instance_name=instance_name,
            cwd=cwd,
            mode=mode,
            project=project,
            remote=remote,
            env=kwargs.get("env"),
        )

        logger.warning("Executing in container: %s", shlex.join(command))

        return runner(command, **kwargs)  # pylint: disable=subprocess-run-check

    def file_pull(
        self,
        *,
        instance_name: str,
        source: pathlib.Path,
        destination: pathlib.Path,
        create_dirs: bool = True,
        recursive: bool = False,
        project: str = "default",
        remote: str = "local",
    ) -> None:
        """Retrieve file from instance_name."""
        command = [
            "file",
            "pull",
            f"{remote}:{instance_name}{source.as_posix()}",
            destination.as_posix(),
        ]

        if create_dirs:
            command.append("--create-dirs")

        if recursive:
            command.append("--recursive")

        try:
            self._run(
                command,
                capture_output=True,
                check=True,
                project=project,
            )
        except subprocess.CalledProcessError as error:
            raise LXDError.from_called_process_error(
                brief=f"Failed to pull file {str(source)!r} from instance {instance_name!r}.",
                error=error,
            )

    def file_push(
        self,
        *,
        instance_name: str,
        source: pathlib.Path,
        destination: pathlib.Path,
        create_dirs: bool = False,
        recursive: bool = False,
        gid: int = -1,
        uid: int = -1,
        mode: Optional[str] = None,
        project: str = "default",
        remote: str = "local",
    ) -> None:
        """Create file with content and file mode."""
        command = [
            "file",
            "push",
            source.as_posix(),
            f"{remote}:{instance_name}{destination.as_posix()}",
        ]

        if create_dirs:
            command.append("--create-dirs")

        if recursive:
            command.append("--recursive")

        if mode:
            command.append(f"--mode={mode}")

        if gid != -1:
            command.append(f"--gid={gid}")

        if uid != -1:
            command.append(f"--uid={gid}")

        try:
            self._run(
                command,
                capture_output=True,
                check=True,
                project=project,
            )
        except subprocess.CalledProcessError as error:
            raise LXDError.from_called_process_error(
                brief=f"Failed to push file {str(source)!r} to instance {instance_name!r}.",
                error=error,
            )

    def info(
        self, *, project: str = "default", remote: str = "local"
    ) -> Dict[str, Any]:
        """Get server config that instance_name is running on."""
        command = ["info", remote + ":"]

        try:
            proc = self._run(
                command,
                capture_output=True,
                check=True,
                project=project,
            )
        except subprocess.CalledProcessError as error:
            raise LXDError.from_called_process_error(
                brief=f"Failed to get info for remote {remote!r}.",
                error=error,
            )

        return _load_yaml(proc.stdout)

    def launch(
        self,
        *,
        config_keys: Dict[str, str],
        image: str,
        image_remote: str,
        instance_name: str,
        ephemeral: bool = False,
        project: str = "default",
        remote: str = "local",
    ) -> None:
        """Launch instance_name."""
        command = [
            "launch",
            f"{image_remote}:{image}",
            f"{remote}:{instance_name}",
        ]

        if ephemeral:
            command.append("--ephemeral")

        for config_key in [f"{k}={v}" for k, v in config_keys.items()]:
            command.extend(["--config", config_key])

        try:
            self._run(
                command,
                capture_output=True,
                check=True,
                project=project,
            )
        except subprocess.CalledProcessError as error:
            raise LXDError.from_called_process_error(
                brief=f"Failed to launch instance {instance_name!r}.",
                error=error,
            )

    def image_copy(
        self,
        *,
        image: str,
        image_remote: str,
        alias: str,
        project: str = "default",
        remote: str = "local",
    ) -> None:
        """Copy image."""
        command = [
            "image",
            "copy",
            f"{image_remote}:{image}",
            f"{remote}:",
            f"--alias={alias}",
        ]

        try:
            self._run(
                command,
                capture_output=True,
                check=True,
                project=project,
            )
        except subprocess.CalledProcessError as error:
            raise LXDError.from_called_process_error(
                brief=f"Failed to copy image {image!r}.",
                error=error,
            )

    def image_delete(
        self, *, image: str, project: str = "default", remote: str = "local"
    ) -> None:
        """Delete image."""
        command = [
            "image",
            "delete",
            f"{remote}:{image}",
        ]

        try:
            self._run(
                command,
                capture_output=True,
                check=True,
                project=project,
            )
        except subprocess.CalledProcessError as error:
            raise LXDError.from_called_process_error(
                brief=f"Failed to delete image {image!r}.",
                error=error,
            )

    def image_list(
        self, *, project: str = "default", remote: str = "local"
    ) -> List[Dict[str, Any]]:
        """List instance_names."""
        command = ["image", "list", f"{remote}:", "--format=yaml"]

        try:
            proc = self._run(
                command,
                capture_output=True,
                check=True,
                project=project,
            )
        except subprocess.CalledProcessError as error:
            raise LXDError.from_called_process_error(
                brief=f"Failed to list images for project {project!r}.",
                error=error,
            )

        return _load_yaml(proc.stdout)

    def list(
        self,
        *,
        instance_name: Optional[str] = None,
        project: str = "default",
        remote: str = "local",
    ) -> List[Dict[str, Any]]:
        """List instances."""
        command = ["list", "--format=yaml"]
        if instance_name is None:
            instance_name = ""

        command.append(f"{remote}:{instance_name}")

        try:
            proc = self._run(
                command,
                capture_output=True,
                check=True,
                project=project,
            )
        except subprocess.CalledProcessError as error:
            raise LXDError.from_called_process_error(
                brief=f"Failed to list instances for project {project!r}.",
                error=error,
            )

        return _load_yaml(proc.stdout)

    def profile_edit(
        self,
        *,
        profile: str,
        config: Dict[str, Any],
        project: str = "default",
        remote: str = "local",
    ) -> None:
        """Edit profile."""
        command = ["profile", "edit", f"{remote}:{profile}"]
        encoded_config = yaml.dump(config).encode()

        try:
            self._run(
                command,
                capture_output=True,
                check=True,
                project=project,
                input=encoded_config,
            )
        except subprocess.CalledProcessError as error:
            raise LXDError.from_called_process_error(
                brief=f"Failed to set profile {profile!r}.",
                error=error,
            )

    def profile_show(
        self, *, profile: str, project: str = "default", remote: str = "local"
    ) -> Dict[str, Any]:
        """Get profile."""
        command = ["profile", "show", f"{remote}:{profile}"]

        try:
            proc = self._run(
                command,
                capture_output=True,
                check=True,
                project=project,
            )
        except subprocess.CalledProcessError as error:
            raise LXDError.from_called_process_error(
                brief=f"Failed to get profile {profile!r}.",
                error=error,
            )

        return _load_yaml(proc.stdout)

    def project_create(self, *, project: str, remote: str = "local") -> None:
        """Create project."""
        command = ["project", "create", f"{remote}:{project}"]

        try:
            self._run(
                command,
                capture_output=True,
                check=True,
                project=project,
            )
        except subprocess.CalledProcessError as error:
            raise LXDError.from_called_process_error(
                brief=f"Failed to create project {project!r}.",
                error=error,
            )

    def project_list(self, remote: str = "local") -> List[str]:
        """Get list of projects.

        :returns: dictionary with remote name mapping to config.
        """
        command = ["project", "list", remote, "--format=yaml"]

        try:
            proc = self._run(
                command,
                capture_output=True,
                check=True,
            )
        except subprocess.CalledProcessError as error:
            raise LXDError.from_called_process_error(
                brief=f"Failed to list projects on remote {remote!r}.",
                error=error,
            )

        projects = _load_yaml(proc.stdout)
        return sorted([p["name"] for p in projects])

    def project_delete(self, *, project: str, remote: str = "local") -> None:
        """Delete project, if exists."""
        command = ["project", "delete", f"{remote}:{project}"]

        try:
            self._run(
                command,
                capture_output=True,
                check=True,
                project=project,
            )
        except subprocess.CalledProcessError as error:
            raise LXDError.from_called_process_error(
                brief=f"Failed to delete project {project!r}.",
                error=error,
            )

    def publish(
        self,
        *,
        alias: str,
        instance_name: str,
        project: str,
        force: bool = True,
        remote: str = "local",
    ) -> None:
        """Create project."""
        command = ["publish", "--alias", alias, f"{remote}:{instance_name}"]
        if force:
            command.append("--force")

        try:
            self._run(
                command,
                capture_output=True,
                check=True,
                project=project,
            )
        except subprocess.CalledProcessError as error:
            raise LXDError.from_called_process_error(
                brief=f"Failed to publish image from {instance_name!r}.",
                error=error,
            )

    def remote_add(self, *, remote: str, addr: str, protocol: str) -> None:
        """Add a public remote."""
        command = ["remote", "add", remote, addr, f"--protocol={protocol}"]

        try:
            self._run(
                command,
                capture_output=True,
                check=True,
            )
        except subprocess.CalledProcessError as error:
            raise LXDError.from_called_process_error(
                brief=f"Failed to add remote {remote!r}.",
                error=error,
            )

    def remote_list(self) -> Dict[str, Any]:
        """Get list of remotes.

        :returns: dictionary with remote name mapping to config.
        """
        command = ["remote", "list", "--format=yaml"]

        try:
            proc = self._run(
                command,
                capture_output=True,
                check=True,
            )
        except subprocess.CalledProcessError as error:
            raise LXDError.from_called_process_error(
                brief="Failed to list remotes.",
                error=error,
            )

        return _load_yaml(proc.stdout)

    def setup(self) -> None:
        """(Re)Setup lxc wrapper."""
        if self.lxc_path.exists():
            return

        lxc_path = shutil.which("lxc")
        if lxc_path is None:
            lxc_path = "/snap/bin/lxc"

        self.lxc_path = pathlib.Path(lxc_path)
        if not self.lxc_path.exists():
            raise RuntimeError("lxc not found in PATH.")

    def start(
        self, *, instance_name: str, project: str = "default", remote: str = "local"
    ) -> None:
        """Start container."""
        command = ["start", f"{remote}:{instance_name}"]

        try:
            self._run(
                command,
                capture_output=True,
                check=True,
                project=project,
            )
        except subprocess.CalledProcessError as error:
            raise LXDError.from_called_process_error(
                brief=f"Failed to start {instance_name!r}.",
                error=error,
            )

    def stop(
        self,
        *,
        instance_name: str,
        project: str = "default",
        remote: str = "local",
        force=True,
        timeout: int = -1,
    ) -> None:
        """Stop container."""
        command = ["stop", f"{remote}:{instance_name}"]

        if force:
            command.append("--force")

        if timeout != -1:
            command.append(f"--timeout={timeout}")

        try:
            self._run(
                command,
                capture_output=True,
                check=True,
                project=project,
            )
        except subprocess.CalledProcessError as error:
            raise LXDError.from_called_process_error(
                brief=f"Failed to stop {instance_name!r}.",
                error=error,
            )


def purge_project(*, lxc: LXC, project: str = "default", remote: str = "local") -> None:
    """Remove project and any associated bits."""
    # with contextlib.suppress(subprocess.CalledProcessError):
    projects = lxc.project_list(remote=remote)
    if project not in projects:
        logger.warning("Attempted to purge non-existent project '%s'.", project)
        return

    # Cleanup any outstanding instance_names.
    for instance_name in lxc.list(project=project):
        logger.warning("Deleting instance_name '%s'.", instance_name)
        lxc.delete(
            instance_name=instance_name["name"],
            project=project,
            remote=remote,
            force=True,
        )

    # Cleanup any outstanding images.
    for image in lxc.image_list(project=project):
        logger.warning("Deleting image '%s'.", image)
        lxc.image_delete(image=image["fingerprint"], project=project, remote=remote)

    # Cleanup project.
    logger.warning("Deleting project '%s'.", project)
    lxc.project_delete(project=project, remote=remote)
