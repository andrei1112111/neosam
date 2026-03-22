from .welcome import WelcomePage
from .whoisi2p import WhoIsI2P
from .installation_guide import InstallationGuide_macos, InstallationGuide_linux, InstallationGuide_windown
from .check_installation import CheckInstallationPage

quick_start = [
    WelcomePage,
    WhoIsI2P,
    InstallationGuide_macos,
    InstallationGuide_linux,
    InstallationGuide_windown,
    CheckInstallationPage,
]

__all__ = [
    "quick_start"
]
