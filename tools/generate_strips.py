import imagedefs

groups = {}
allstrips = {}

for n, filename in enumerate(imagedefs.all_images):
    g, fn = filename.split("/", -1)
    fn = fn.rsplit(".", 1)[0]
    #fn = fn.replace(".", "_")
    if fn.startswith("0") or fn.startswith("1"):
        fn = "_" + fn
    groups.setdefault(g, []).append(fn)
    allstrips[fn] = n

print()
print()
print("class strips:")
for g, l in groups.items():
    print("    class %s:" % g)
    for i in l:
        print("        %s = %d" % (i, allstrips[i]))
    print()


print("all_strips = [")
for fn in allstrips:
    print("    %s_data," % fn)
print("]")
