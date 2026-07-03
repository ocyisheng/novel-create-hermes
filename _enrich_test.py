"""Test just the YAML loading part."""
import yaml, os, time

OLD_WB = "novels/空山闻仙/worldbuilding"
files = [f for f in os.listdir(OLD_WB) if f.endswith(".yaml")]
print(f"Found {len(files)} YAML files")

t0 = time.time()
for fname in files[:3]:
    fpath = os.path.join(OLD_WB, fname)
    data = yaml.safe_load(open(fpath, "r", encoding="utf-8"))
    print(f"  {fname}: {len(str(data))} bytes, keys={list(data.keys())}")
print(f"Took {time.time()-t0:.2f}s")
