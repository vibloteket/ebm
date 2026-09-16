// One build-generated manifest, shared by every Pyodide entrypoint.
export async function loadPythonPackage(pyodide) {
  const response = await fetch('./python-files.json', {cache: 'no-store'});
  if (!response.ok) throw new Error(`Python manifest: HTTP ${response.status}`);
  const files = await response.json();
  if (!Array.isArray(files) || !files.length) throw new Error('Empty Python manifest');
  pyodide.FS.mkdirTree('/ebm');
  for (const file of files) {
    if (typeof file !== 'string' || !file.endsWith('.py') || file.split('/').some(part => !part || part === '.' || part === '..') || file.includes('\\')) {
      throw new Error(`Invalid Python package path: ${file}`);
    }
    const source = await fetch(`./ebm/${file}`, {cache: 'no-store'});
    if (!source.ok) throw new Error(`${file}: HTTP ${source.status}`);
    const destination = `/ebm/${file}`;
    pyodide.FS.mkdirTree(destination.slice(0, destination.lastIndexOf('/')));
    pyodide.FS.writeFile(destination, await source.text());
  }
  pyodide.runPython("import sys\nif '/' not in sys.path: sys.path.insert(0, '/')");
}
