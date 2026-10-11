// Presentation links load only published code from this emulator's own tree.
export async function launchConfiguration(href, fetchFile = fetch) {
  const location = new URL(href);
  const slug = location.searchParams.get("game");
  const checkpoint = location.searchParams.get("checkpoint");
  if (!slug && !checkpoint) return {};
  if (!slug || !/^[a-z_][a-z0-9_]*\.[a-z_][a-z0-9_]*$/.test(slug)) {
    throw new Error("Invalid game link: expected group.game");
  }
  const config = { autostartSlug: slug };
  if (checkpoint !== null) {
    if (!/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(checkpoint)) {
      throw new Error("Invalid presentation checkpoint");
    }
    const [group, name] = slug.split(".");
    const directory = `games/${group}/${name}/code/`;
    const source = new URL(`${directory}checkpoints/${checkpoint}.py`, new URL("./", location));
    const response = await fetchFile(source, { cache: "no-cache" });
    if (!response.ok) throw new Error(`Checkpoint ${checkpoint} could not be loaded (${response.status})`);
    config.workspaceFiles = [{ path: `${directory}${name}.py`,
      content: await response.text(), encoding: "utf8" }];
  }
  return config;
}
