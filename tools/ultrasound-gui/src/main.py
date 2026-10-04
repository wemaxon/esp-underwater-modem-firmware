from pathlib import Path

from ultrasound_gui.ui.app import Application


def main():
    Application(link_file=Path.home() / ".underwater-modem-toolbox" / "link.json").mainloop()


if __name__ == "__main__":
    main()
