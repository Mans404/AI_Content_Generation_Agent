from pathlib import Path


class PromptLoader:
    def __init__(self):
        self.dir = Path(__file__).parent / "prompts"

    def _read(self, name: str) -> str:
        return (self.dir / name).read_text(encoding="utf-8")

    def system(self, **kwargs) -> str:
        return self._read("system.txt").format(**kwargs)

    def user(self, **kwargs) -> str:
        return self._read("user.txt").format(**kwargs)