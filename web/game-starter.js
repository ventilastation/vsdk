// Files created by the browser IDE's New Game action. New games use VS2.
export function createGameFiles(info, className) {
  const source = [
    "import vs2",
    "",
    "",
    `class ${className}(vs2.Scene):`,
    "    def build(self):",
    "        # Create layers and drawables here; see the first-game tutorial.",
    "        pass",
    "",
    "    def update(self):",
    "        pass",
    "",
    "",
    "def main():",
    `    return ${className}()`,
    "",
  ].join("\n");
  return {
    [`${info.key}/code/${info.slug}.py`]: source,
    [`${info.key}/meta.json`]: JSON.stringify({
      api: "vs2", api_revision: 2, title: info.slug,
    }, null, 2) + "\n",
    [`${info.key}/images/__images__.yaml`]: "palettegroups:\n  palette1: []\n",
    [`${info.key}/sounds/.gitkeep`]: "",
  };
}
