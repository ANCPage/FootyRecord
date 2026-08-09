import glob

for f in glob.glob('Core/visualize_*.py') + ['generate_round_images.py']:
    with open(f, encoding='utf-8') as fh:
        content = fh.read()
    content = content.replace("start, end = edge;", "start, end = edge.source, edge.target;")
    content = content.replace("for (s, e), v in sorted_items", "for edge_obj, v in sorted_items: s, e = edge_obj.source, edge_obj.target")
    # Wait, the list comprehension:
    # [[f'{safe_label(s)} -> {safe_label(e)}', f'{abs(v):.2f}', n_a if v > 0 else n_b] for (s, e), v in sorted_items]
    # This is a list comprehension. We can't do assignment inside it easily.
    content = content.replace(
        "[[f'{safe_label(s)} -> {safe_label(e)}', f'{abs(v):.2f}', n_a if v > 0 else n_b] for (s, e), v in sorted_items]",
        "[[f'{safe_label(edge_obj.source)} -> {safe_label(edge_obj.target)}', f'{abs(v):.2f}', n_a if v > 0 else n_b] for edge_obj, v in sorted_items]"
    )
    with open(f, 'w', encoding='utf-8', newline='') as fh:
        fh.write(content)
