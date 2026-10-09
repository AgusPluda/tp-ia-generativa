"""Los scripts montados en el contenedor de Linux conservan fin de línea LF en cualquier clon (CE-005)."""

from gym_agent.config import REPO_ROOT


def test_los_scripts_sh_se_clonan_con_lf():
    lineas = (REPO_ROOT / ".gitattributes").read_text(encoding="utf-8").splitlines()
    assert any(l.split()[:1] == ["*.sh"] and "eol=lf" in l for l in lineas)
