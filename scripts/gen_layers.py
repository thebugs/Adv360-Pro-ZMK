#!/usr/bin/env python3
"""Regenerate layers derived from the base layer in config/adv360.keymap.

Bilateral home row mods (BHRM), port of sunaku's Glorious Engrammer BHRM (also used by TailorKey).

Base layer HRM keys must be bound as `&hrm_<l|r>_<index|middle|ring|pinky> MOD KEY`.
From those the script (re)writes:
  - hrm_<h>_<f>            base hold-taps (timings kept if node already exists)
  - hrm_<h>_<f>_<f2>       chord hold-taps for same-hand mod stacking
  - hrm_<h>_<f>_hold/_tap  macros
  - finger_<h>_<f>         finger layers, regenerated in place (appended on first run)

NumWord, plain ZMK take on urob's num-word: toggle the `numword` layer on, digits and
number punctuation keep it on, any other key is typed and turns it off.
  - numword                layer, regenerated in place (appended on first run)
  - numword_exit           macro typing a key and toggling numword off

Run after changing base layer keys or HRM timings in Keymap Editor:
    python3 scripts/gen_layers.py [path/to/adv360.keymap]
"""

import re
import sys
from pathlib import Path

KEYMAP = Path(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).parent.parent / "config/adv360.keymap")

KEYS_L = [*range(0, 7), *range(14, 21), *range(28, 35), *range(46, 52), *range(60, 65)]
KEYS_R = [*range(7, 14), *range(21, 28), *range(39, 46), *range(54, 60), *range(71, 76)]
THUMBS_L = [35, 36, 52, 65, 66, 67]
THUMBS_R = [37, 38, 53, 68, 69, 70]
HAND = {
    "l": {"keys": KEYS_L, "thumbs": THUMBS_L},
    "r": {"keys": KEYS_R, "thumbs": THUMBS_R},
}
# Keymap rows, used only to format finger layer bindings
ROWS = [
    [*range(0, 14)],
    [*range(14, 28)],
    [*range(28, 46)],
    [*range(46, 60)],
    [*range(60, 76)],
]
FINGERS = ["index", "middle", "ring", "pinky"]
# sunaku GE v52 defaults: 150ms resolution + 30ms per finger, 150ms streak decay, 300ms repeat
DEFAULTS = {
    "index": {"tapping-term-ms": 180},
    "middle": {"tapping-term-ms": 210},
    "ring": {"tapping-term-ms": 240},
    "pinky": {"tapping-term-ms": 270},
}
DEFAULT_COMMON = {"flavor": '"tap-preferred"', "quick-tap-ms": 300, "require-prior-idle-ms": 150}
ALL_MODS = "<&kp LSHFT>, <&kp RSHFT>, <&kp LALT>, <&kp RALT>, <&kp LCTRL>, <&kp RCTRL>, <&kp LGUI>, <&kp RGUI>"

NUMWORD_LAYER = "numword"
# Right hand numpad, same spots as on the Kp layer
NUMWORD_KEYS = {
    10: "EQUAL", 11: "FSLH", 12: "STAR",
    23: "N7", 24: "N8", 25: "N9", 26: "MINUS",
    41: "N4", 42: "N5", 43: "N6", 44: "PLUS",
    55: "N1", 56: "N2", 57: "N3",
    70: "N0", 73: "DOT",
}
# Base layer keys that keep NumWord on, other keys exit it
NUMWORD_CONTINUE = {
    *(f"N{i}" for i in range(10)),
    "DOT", "COMMA", "MINUS", "PLUS", "STAR", "FSLH", "EQUAL", "COLON", "BSPC", "DELETE", "DEL",
}

HRM_RE = re.compile(r"^&hrm_([lr])_(index|middle|ring|pinky)\s+(\S+)\s+(\S+)$")
GENERATED_NODE_RE = re.compile(r"^hrm_[lr]_(index|middle|ring|pinky)(_(index|middle|ring|pinky|hold|tap))?$")
FINGER_LAYER_RE = re.compile(r"^finger_[lr]_(index|middle|ring|pinky)$")


def find_close(text, open_idx):
    """Index just past the `};` closing the brace at open_idx."""
    depth = 0
    for i in range(open_idx, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                end = text.index(";", i) + 1
                return end
    raise ValueError("unbalanced braces")


def children(text, open_idx, close_idx):
    """Yield (name, label, start, open, end) for direct child nodes of a block."""
    node_re = re.compile(r"(?:([\w-]+)\s*:\s*)?([\w-]+)\s*\{")
    i = open_idx + 1
    while True:
        m = node_re.search(text, i, close_idx)
        if not m:
            return
        start = text.rfind("\n", 0, m.start()) + 1
        open_ = m.end() - 1
        end = find_close(text, open_)
        yield m.group(2), m.group(1), start, open_, end
        i = end


def root_block(text, name):
    m = re.search(rf"^\s*{name}\s*\{{", text, re.M)
    if not m:
        return None
    open_ = m.end() - 1
    return m.start(), open_, find_close(text, open_)


def prop(body, name):
    m = re.search(rf"{name}\s*=\s*(<[^>]*>|\"[^\"]*\")\s*;", body)
    if not m:
        return None
    value = m.group(1)
    return int(value[1:-1]) if value.startswith("<") else value


def split_bindings(body):
    m = re.search(r"bindings\s*=\s*<(.*?)>\s*;", body, re.S)
    return [b.strip() for b in re.findall(r"&[^&]+", m.group(1))]


def node(label, props, indent="        "):
    lines = [f"{indent}{label}: {label} {{"]
    lines += [f"{indent}    {p}" for p in props]
    lines.append(f"{indent}}};")
    return "\n".join(lines)


def hold_tap(label, timing, triggers, bindings):
    return node(label, [
        'compatible = "zmk,behavior-hold-tap";',
        "#binding-cells = <2>;",
        f"bindings = {bindings};",
        f"flavor = {timing['flavor']};",
        f"tapping-term-ms = <{timing['tapping-term-ms']}>;",
        f"quick-tap-ms = <{timing['quick-tap-ms']}>;",
        f"require-prior-idle-ms = <{timing['require-prior-idle-ms']}>;",
        "hold-trigger-on-release;",
        f"hold-trigger-key-positions = <{' '.join(map(str, triggers))}>;",
    ])


def macro(label, bindings):
    return node(label, [
        'compatible = "zmk,behavior-macro-one-param";',
        "#binding-cells = <1>;",
        "wait-ms = <0>;",
        "tap-ms = <0>;",
        f"bindings = {bindings};",
    ])


def format_layer(bindings):
    width = max(len(b) for b in bindings)
    rows = ["  ".join(bindings[p].ljust(width) for p in row).rstrip() for row in ROWS]
    return "\n".join(rows)


def append_to(text, block, content):
    _, _, close = root_block(text, block)
    insert_at = text.rfind("}", 0, close)
    insert_at = text.rfind("\n", 0, insert_at) + 1
    return text[:insert_at] + "\n" + content + "\n" + text[insert_at:]


def remove_nodes(text, block, labels):
    b = root_block(text, block)
    removals = [(start, end) for name, label, start, _, end in children(text, b[1], b[2]) if (label or name) in labels]
    for start, end in sorted(removals, reverse=True):
        stop = end + 1 if text[end:end + 1] == "\n" else end
        text = text[:start] + text[stop:]
    return text


def layer_node(name, display, bindings):
    body = "\n".join("                " + line for line in format_layer(bindings).splitlines())
    return (
        f"        {name} {{\n"
        f'            display-name = "{display}";\n'
        f"            bindings = <\n{body}\n            >;\n"
        f"        }};"
    )


def numword(text):
    _, km_open, km_close = root_block(text, "keymap")
    layers = list(children(text, km_open, km_close))
    names = [layer[0] for layer in layers]
    base = split_bindings(text[layers[0][3]:layers[0][4]])
    index = names.index(NUMWORD_LAYER) if NUMWORD_LAYER in names else len(names)

    # Hold-taps with &kp as tap (&lt, HRMs, thumbs) exit with their tap key
    tap_behaviors = {"lt"} | {
        m.group(1) for m in re.finditer(r"(\w+)\s*:\s*[\w-]+\s*\{[^{}]*?bindings\s*=\s*<[^>]*>\s*,\s*<&kp>\s*;", text)
    }
    bindings = []
    for pos, binding in enumerate(base):
        parts = binding.split()
        key = None
        if pos in NUMWORD_KEYS:
            key = NUMWORD_KEYS[pos]
        elif parts[0] == "&kp" and len(parts) == 2:
            key = parts[1]
        elif parts[0][1:] in tap_behaviors and len(parts) == 3:
            key = parts[2]
        if key is None:
            bindings.append("&trans")
        elif pos in NUMWORD_KEYS or key in NUMWORD_CONTINUE:
            bindings.append(f"&kp {key}")
        else:
            bindings.append(f"&numword_exit {key}")

    node = layer_node(NUMWORD_LAYER, "NumWord", bindings)
    if NUMWORD_LAYER in names:
        _, _, start, _, end = layers[index]
        text = text[:start] + node + text[end:]
    else:
        text = append_to(text, "keymap", node)

    text = remove_nodes(text, "macros", {"numword_exit"})
    return append_to(text, "macros", macro(
        "numword_exit",
        f"<&macro_tap>, <&macro_param_1to1>, <&kp A>, <&macro_tap>, <&tog {index}>",
    ))


def main():
    text = KEYMAP.read_text()

    # Layers: base is the first one, finger layers must be the last ones
    _, km_open, km_close = root_block(text, "keymap")
    layers = list(children(text, km_open, km_close))
    names = [layer[0] for layer in layers]
    finger_idx = [i for i, n in enumerate(names) if FINGER_LAYER_RE.match(n)]
    if finger_idx and finger_idx != list(range(finger_idx[0], finger_idx[0] + len(finger_idx))):
        sys.exit("finger_* layers must be next to each other; move other layers out from between them first")
    first_finger = finger_idx[0] if finger_idx else len(names)
    base = split_bindings(text[layers[0][3]:layers[0][4]])
    if len(base) != 76:
        sys.exit(f"base layer has {len(base)} bindings, expected 76")

    hrms = {}  # (hand, finger) -> {pos, mod, key}
    for pos, binding in enumerate(base):
        m = HRM_RE.match(binding)
        if m:
            hrms[(m.group(1), m.group(2))] = {"pos": pos, "mod": m.group(3), "key": m.group(4)}
    if not hrms:
        sys.exit("no &hrm_<h>_<finger> MOD KEY bindings found in base layer")

    # Layer-tap style behaviors (hold = &mo) become plain &mo on same-side thumbs
    mo_behaviors = {"lt"} | {
        m.group(1) for m in re.finditer(r"(\w+)\s*:\s*[\w-]+\s*\{[^{}]*?bindings\s*=\s*<&mo>\s*,", text)
    }

    # Keep timings of existing base hold-taps so they can be tuned in Keymap Editor
    _, bh_open, bh_close = root_block(text, "behaviors")
    timings = {}
    for (hand, finger) in hrms:
        timing = {**DEFAULT_COMMON, **DEFAULTS[finger]}
        for name, label, _, open_, end in children(text, bh_open, bh_close):
            if (label or name) == f"hrm_{hand}_{finger}":
                body = text[open_:end]
                for p in timing:
                    value = prop(body, p)
                    if value is not None:
                        timing[p] = value
        timings[(hand, finger)] = timing

    behaviors, macros, finger_layers = [], [], []
    for i, ((hand, finger), hrm) in enumerate(sorted(hrms.items(), key=lambda x: (x[0][0], FINGERS.index(x[0][1])))):
        name = f"hrm_{hand}_{finger}"
        other = "r" if hand == "l" else "l"
        triggers = sorted(HAND[other]["keys"] + HAND[other]["thumbs"])
        layer = first_finger + i
        timing = timings[(hand, finger)]

        behaviors.append(hold_tap(name, timing, triggers, f"<&{name}_hold>, <&kp>"))
        macros.append(macro(f"{name}_hold",
            f"<&macro_press>, <&macro_param_1to1>, <&kp A>, <&mo {layer}>, <&macro_pause_for_release>, "
            f"<&macro_release>, <&macro_param_1to1>, <&kp A>, <&mo {layer}>"))
        macros.append(macro(f"{name}_tap",
            f"<&macro_release>, {ALL_MODS}, <&macro_tap>, <&kp {hrm['key']}>, "
            f"<&macro_tap>, <&macro_param_1to1>, <&kp A>"))

        layer_bindings = ["&trans"] * 76
        same_hand = HAND[hand]["keys"]
        for pos in same_hand:
            m = re.match(r"^&kp\s+(\S+)$", base[pos])
            if m:
                layer_bindings[pos] = f"&{name}_tap {m.group(1)}"
        for pos in HAND[hand]["thumbs"]:
            parts = base[pos].split()
            if parts[0] == "&kp" and len(parts) == 2:
                layer_bindings[pos] = f"&{name}_tap {parts[1]}"
            elif parts[0][1:] in mo_behaviors:
                layer_bindings[pos] = f"&mo {parts[1]}"
        for (h2, f2), other_hrm in hrms.items():
            if h2 != hand:
                continue
            if f2 == finger:
                layer_bindings[other_hrm["pos"]] = "&none"
                continue
            chord = f"{name}_{f2}"
            behaviors.append(hold_tap(chord, timing, triggers, f"<&kp>, <&{name}_tap>"))
            layer_bindings[other_hrm["pos"]] = f"&{chord} {other_hrm['mod']} {other_hrm['key']}"

        display = f"{'L' if hand == 'l' else 'R'}{finger.capitalize()}"
        finger_layers.append(layer_node(f"finger_{hand}_{finger}", display, layer_bindings))

    # Finger layers are replaced in place so layers after them keep their indexes
    if finger_idx:
        start, end = layers[finger_idx[0]][2], layers[finger_idx[-1]][4]
        text = text[:start] + "\n\n".join(finger_layers) + text[end:]

    # Drop previously generated nodes, back to front so offsets stay valid
    removals = []
    for block in ("behaviors", "macros"):
        b = root_block(text, block)
        if not b:
            continue
        for name, label, start, _, end in children(text, b[1], b[2]):
            if GENERATED_NODE_RE.match(label or name):
                removals.append((start, end))
    for start, end in sorted(removals, reverse=True):
        stop = end + 1 if text[end:end + 1] == "\n" else end
        text = text[:start] + text[stop:]

    text = append_to(text, "behaviors", "\n\n".join(behaviors))
    if not root_block(text, "macros"):
        _, _, bh_close = root_block(text, "behaviors")
        text = text[:bh_close] + "\n\n    macros {\n    };" + text[bh_close:]
    text = append_to(text, "macros", "\n\n".join(macros))
    if not finger_idx:
        text = append_to(text, "keymap", "\n\n".join(finger_layers))
    text = numword(text)
    text = re.sub(r"\{\n\n+", "{\n", text)
    text = re.sub(r"\n\n+(\s*\};)", r"\n\1", text)
    text = re.sub(r"\n[ \t]*\n([ \t]*\n)+", "\n\n", text)

    KEYMAP.write_text(text)
    print(f"{len(hrms)} HRMs, finger layers {first_finger}-{first_finger + len(hrms) - 1}")


if __name__ == "__main__":
    main()
