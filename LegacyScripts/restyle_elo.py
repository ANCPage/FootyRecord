import re

# 1. Revert header injections in visualize_matchup.py
with open("Core/visualize_matchup.py", "r", encoding="utf-8") as f:
    code = f.read()

code = code.replace(
    "fig.suptitle(f'STRATEGIC MATCHUP: {n_a.upper()} ({int(elo_a)}) VS {n_b.upper()} ({int(elo_b)})', color=self.text_color, fontsize=18, y=0.97, fontproperties=self.prop_title)",
    "fig.suptitle(f'STRATEGIC MATCHUP: {n_a.upper()} VS {n_b.upper()}', color=self.text_color, fontsize=18, y=0.97, fontproperties=self.prop_title)"
)

code = code.replace(
    "fig_m.suptitle(f'MATCHUP: {n_a.upper()} ({int(elo_a)}) VS {n_b.upper()} ({int(elo_b)})', color=self.text_color, fontsize=16, y=0.985, fontproperties=self.prop_title)",
    "fig_m.suptitle(f'MATCHUP: {n_a.upper()} VS {n_b.upper()}', color=self.text_color, fontsize=16, y=0.985, fontproperties=self.prop_title)"
)

# Update _add_color_key to include Rating labels
old_key_func = """    def _add_color_key(self, fig, n_a, c_a, n_b, c_b, y_pos=0.05):
        fig.text(0.35, y_pos, n_a.upper(), color=self.text_color, fontsize=12, ha='right', va='center', fontproperties=self.prop_sub)
        fig.add_artist(patches.Rectangle((0.36, y_pos-0.008), 0.02, 0.016, color=c_a, transform=fig.transFigure))
        fig.text(0.5, y_pos, "VS", color=self.sub_text_color, fontsize=12, ha='center', va='center', fontproperties=self.prop_sub)
        fig.add_artist(patches.Rectangle((0.62, y_pos-0.008), 0.02, 0.016, color=c_b, transform=fig.transFigure))
        fig.text(0.65, y_pos, n_b.upper(), color=self.text_color, fontsize=12, ha='left', va='center', fontproperties=self.prop_sub)"""

new_key_func = """    def _add_color_key(self, fig, n_a, c_a, n_b, c_b, elo_a, elo_b, y_pos=0.05):
        fig.text(0.35, y_pos, n_a.upper(), color=self.text_color, fontsize=12, ha='right', va='center', fontproperties=self.prop_sub)
        fig.text(0.35, y_pos - 0.02, f"RATING: {int(elo_a)}", color=self.sub_text_color, fontsize=9, ha='right', va='center', fontproperties=self.prop_body)
        
        fig.add_artist(patches.Rectangle((0.36, y_pos-0.008), 0.02, 0.016, color=c_a, transform=fig.transFigure))
        fig.text(0.5, y_pos, "VS", color=self.sub_text_color, fontsize=12, ha='center', va='center', fontproperties=self.prop_sub)
        
        fig.add_artist(patches.Rectangle((0.62, y_pos-0.008), 0.02, 0.016, color=c_b, transform=fig.transFigure))
        fig.text(0.65, y_pos, n_b.upper(), color=self.text_color, fontsize=12, ha='left', va='center', fontproperties=self.prop_sub)
        fig.text(0.65, y_pos - 0.02, f"RATING: {int(elo_b)}", color=self.sub_text_color, fontsize=9, ha='left', va='center', fontproperties=self.prop_body)"""

code = code.replace(old_key_func, new_key_func)

# Update calls to _add_color_key
code = code.replace("self._add_color_key(fig, n_a, c_a, n_b, c_b, y_pos=0.06)", "self._add_color_key(fig, n_a, c_a, n_b, c_b, elo_a, elo_b, y_pos=0.06)")
code = code.replace("self._add_color_key(fig_m, n_a, c_a, n_b, c_b, y_pos=0.06)", "self._add_color_key(fig_m, n_a, c_a, n_b, c_b, elo_a, elo_b, y_pos=0.06)")
code = code.replace("self._add_color_key(fig, n_a, c_a, n_b, c_b, y_pos=0.08)", "self._add_color_key(fig, n_a, c_a, n_b, c_b, elo_a, elo_b, y_pos=0.08)")
code = code.replace("self._add_color_key(fig_m, n_a, c_a, n_b, c_b, y_pos=0.06)", "self._add_color_key(fig_m, n_a, c_a, n_b, c_b, elo_a, elo_b, y_pos=0.06)")

with open("Core/visualize_matchup.py", "w", encoding="utf-8") as f:
    f.write(code)

# 2. Revert header injections in visualize_story.py
with open("Core/visualize_story.py", "r", encoding="utf-8") as f:
    story_code = f.read()

story_code = story_code.replace(
    "fig.suptitle(f'TACTICAL STORY: {n_a.upper()} ({int(elo_a)}) VS {n_b.upper()} ({int(elo_b)})', color=self.text_color, fontsize=18, y=0.98, fontproperties=self.prop_title)",
    "fig.suptitle(f'TACTICAL STORY: {n_a.upper()} VS {n_b.upper()}', color=self.text_color, fontsize=18, y=0.98, fontproperties=self.prop_title)"
)

story_code = story_code.replace(
    "fig.text(0.5, title_y, f'TACTICAL STORY:\\n{n_a.upper()} ({int(elo_a)}) VS {n_b.upper()} ({int(elo_b)})', color=self.text_color, fontsize=17, ha='center', va='center', fontproperties=self.prop_title)",
    "fig.text(0.5, title_y, f'TACTICAL STORY:\\n{n_a.upper()} VS {n_b.upper()}', color=self.text_color, fontsize=17, ha='center', va='center', fontproperties=self.prop_title)"
)

# Add Ratings to story footers or keys if available. Story already has attack headers.
story_code = story_code.replace(
    "fig.text(0.15 if not is_mobile else 0.2, text_y_attack, f'{n_b.upper()} ATTACK', color=mute_color(c_b), fontsize=14 * font_scale, ha='center', va='center', fontproperties=self.prop_sub)",
    "fig.text(0.15 if not is_mobile else 0.2, text_y_attack, f'{n_b.upper()} ATTACK\\n(RATING: {int(elo_b)})', color=mute_color(c_b), fontsize=12 * font_scale, ha='center', va='center', fontproperties=self.prop_sub)"
)

story_code = story_code.replace(
    "fig.text(0.85 if not is_mobile else 0.8, text_y_attack, f'{n_a.upper()} ATTACK', color=mute_color(c_a), fontsize=14 * font_scale, ha='center', va='center', fontproperties=self.prop_sub)",
    "fig.text(0.85 if not is_mobile else 0.8, text_y_attack, f'{n_a.upper()} ATTACK\\n(RATING: {int(elo_a)})', color=mute_color(c_a), fontsize=12 * font_scale, ha='center', va='center', fontproperties=self.prop_sub)"
)

with open("Core/visualize_story.py", "w", encoding="utf-8") as f:
    f.write(story_code)

# 3. Clean up visualize_tips.py
with open("Core/visualize_tips.py", "r", encoding="utf-8") as f:
    tips_code = f.read()

# Revert the messy matchup string construction
old_matchup_logic = """            h_name = tip['home_name']
            a_name = tip['away_name']
            
            h_elo = tip.get('home_elo')
            a_elo = tip.get('away_elo')
            
            if h_elo is not None and a_elo is not None:
                matchup_str = f'{h_name} ({int(h_elo)}) vs {a_name} ({int(a_elo)})'
            else:
                matchup_str = f'{h_name} vs {a_name}'
                
            if is_mobile and len(matchup_str) > 28: # Increased limit slightly for ELO
                def get_short_name(n):
                    if n == 'North Melbourne': return 'Nth Melb'
                    if n == 'Port Adelaide': return 'Port Adel'
                    if n == 'West Coast Eagles': return 'West Coast'
                    if n == 'Gold Coast Suns': return 'Gold Coast'
                    if n == 'Sydney Swans': return 'Sydney'
                    if n == 'Geelong Cats': return 'Geelong'
                    if n == 'Western Bulldogs': return 'Bulldogs'
                    if n == 'Adelaide Crows': return 'Adelaide'
                    if n == 'Brisbane Lions': return 'Brisbane'
                    if n == 'GWS Giants': return 'GWS'
                    return n
                
                h_short = get_short_name(h_name)
                a_short = get_short_name(a_name)
                if h_elo is not None and a_elo is not None:
                    matchup_str = f'{h_short} ({int(h_elo)}) vs {a_short} ({int(a_elo)})'
                else:
                    matchup_str = f'{h_short} vs {a_short}'"""

new_matchup_logic = """            h_name = tip['home_name']
            a_name = tip['away_name']
            matchup_str = f'{h_name} vs {a_name}'
            if is_mobile and len(matchup_str) > 22:
                def get_short_name(n):
                    if n == 'North Melbourne': return 'Nth Melb'
                    if n == 'Port Adelaide': return 'Port Adel'
                    if n == 'West Coast Eagles': return 'West Coast'
                    if n == 'Gold Coast Suns': return 'Gold Coast'
                    if n == 'Sydney Swans': return 'Sydney'
                    if n == 'Geelong Cats': return 'Geelong'
                    if n == 'Western Bulldogs': return 'Bulldogs'
                    if n == 'Adelaide Crows': return 'Adelaide'
                    if n == 'Brisbane Lions': return 'Brisbane'
                    if n == 'GWS Giants': return 'GWS'
                    return n
                h_short = get_short_name(h_name)
                a_short = get_short_name(a_name)
                matchup_str = f'{h_short} vs {a_short}'"""

tips_code = tips_code.replace(old_matchup_logic, new_matchup_logic)

# Add ELO context under the Predicted Winner
tips_code = tips_code.replace(
    "plt.text(col_x[2], curr_y, winner_name.upper(), ha='center', va='center', color=txt_color, fontsize=row_fs-1, zorder=2, fontproperties=row_sub_font)",
    "plt.text(col_x[2], curr_y + 0.01, winner_name.upper(), ha='center', va='center', color=txt_color, fontsize=row_fs-1, zorder=2, fontproperties=row_sub_font)\n            winner_elo = tip.get('home_elo') if tip['winner_id'] == tip.get('home_id') else tip.get('away_elo')\n            if winner_elo:\n                plt.text(col_x[2], curr_y - 0.012, f'RATING: {int(winner_elo)}', ha='center', va='center', color=txt_color, fontsize=row_fs-4, zorder=2, fontproperties=self.prop_body, alpha=0.8)"
)

with open("Core/visualize_tips.py", "w", encoding="utf-8") as f:
    f.write(tips_code)

print("Restyled ELO placement for better UX and aesthetic fit.")
