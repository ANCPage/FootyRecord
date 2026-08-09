import re

with open('Core/visualize_ladder.py', 'r', encoding='utf-8') as f:
    code = f.read()

bad_indent = '''        rank_str = f'RANK: {get_ordinal(rank)}' if rank else ''
tier_str = f' [{tier}]' if tier else ''
ax1.set_title(f"{t_data['name'].upper()} {rank_str}{tier_str}:\\n{season} TACTICAL JOURNEY" if is_mobile else f"{t_data['name'].upper()} {rank_str}{tier_str}: {season} TACTICAL JOURNEY", 
                     color=self.text_color, fontsize=title_fs, pad=30, fontproperties=self.prop_title)'''

fixed_indent = '''        rank_str = f'RANK: {get_ordinal(rank)}' if rank else ''
        tier_str = f' [{tier}]' if tier else ''
        ax1.set_title(f"{t_data['name'].upper()} {rank_str}{tier_str}:\\n{season} TACTICAL JOURNEY" if is_mobile else f"{t_data['name'].upper()} {rank_str}{tier_str}: {season} TACTICAL JOURNEY", 
                     color=self.text_color, fontsize=title_fs, pad=30, fontproperties=self.prop_title)'''

code = code.replace(bad_indent, fixed_indent)

with open('Core/visualize_ladder.py', 'w', encoding='utf-8', newline='') as f:
    f.write(code)
