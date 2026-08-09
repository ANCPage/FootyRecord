# Graphic Design & UX Assessment: AFL Tactical Visualizer (V3)

**Date:** April 2026
**Theme Focus:** Retro-Dossier / Industrial Sports
**Typography:** Custom Type Stack (`FasterOne`, `Wallpoet`, `Roboto`)
**Color Palette:** Cream Base (`#F4F1EA`), Charcoal Text (`#3E3A35`), Muted Accents

---

## 1. Executive Summary
The V3 visual update successfully establishes a cohesive, premium identity. By transitioning to a strict typographic hierarchy using imported web fonts and applying a color-muting strategy to data accents, the graphics now feel like an authentic, high-end "scouting dossier" rather than a default Matplotlib output. The introduction of the `TIPS_RESULTS.png` graphic significantly improves the storytelling loop (Expectation vs. Reality) for the user.

## 2. Graphic Design Review

### **Typography & Hierarchy**
*   **The Custom Stack (`Roboto` integration):** Replacing the system default sans-serif with `Roboto` as the body font was a crucial upgrade. It provides a crisp, geometric foundation that contrasts beautifully with the aggressive styling of the headers. The text is highly legible even at small sizes (like the player nodes on the field).
*   **FasterOne & Wallpoet Sizing:** The 30% reduction in `FasterOne` title size resolved the edge-bleeding issues and restored the margins. `FasterOne` now acts as a proper marquee logo at the top of the graphics. Enforcing a minimum size for `Wallpoet` prevents the stencil cuts from blurring, ensuring structural integrity for tabular data.
*   **Overall Readability:** Excellent. The strict rules governing which font is used where (H1 vs H2 vs Body) guide the eye naturally down the page.

### **Color & Texture**
*   **The Muted Accents (`mute_color` function):** This is the strongest design upgrade in V3. High-saturation digital hex codes clash with a vintage cream background. By mathematically blending the team and confidence colors with the cream base (desaturation), the arrows, team tags, and grade blocks now look like they are printed *on* the paper with vintage ink.
*   **Hierarchy of Color:** The charcoal text (`#3E3A35`) sits perfectly on the cream (`#F4F1EA`). The decision to drop the "all vectors" (`_all`) charts was also smart; it removes visual noise and allows the "Top 20" tactical vectors to breathe, making the color-coded arrows much easier to follow.

## 3. User Experience (UX) Assessment

### **Information Architecture**
*   **The "Pre" and "Post" Loop:** The introduction of the `TIPS_RESULTS.png` graphic is a major UX win. Previously, the user was left hanging after the prediction. Now, there is a clear "Before" (Confidence Grades) and "After" (Correct/Incorrect tags with season totals). This closes the loop and gamifies the data.
*   **Clear Call to Actions (CTAs) in Data:** The layout of the tables (especially in the Tips graphic) is highly scannable. Game -> Matchup -> Winner -> Result. The eye tracks left to right effortlessly. 

### **Mobile Responsiveness**
*   **Aspect Ratio (9:16) Handling:** The mobile graphics (InstaReels/InstaPost) have been given proper breathing room. The added margins ensure that critical data isn't cut off by the UI overlays of platforms like Instagram or TikTok. 
*   **Long Name Truncation:** The mobile logic correctly handles long team names (e.g., truncating "North Melbourne" to "Nth Melb"), preventing awkward text wrapping that breaks the tabular layout.

## 4. Recommendations for Future Polish
1.  **Iconography:** To elevate the dossier look further, consider introducing subtle, muted vector icons (e.g., a small target reticle next to the "Predicted Winner" header, or a small field icon next to "Matchup").
2.  **Texture Overlay:** While the cream hex code is great, a very subtle grain or paper texture overlay (applied globally as a semi-transparent PNG mask over the final plots) would perfect the vintage print illusion.
3.  **Dynamic Legend:** The color key (Team A vs Team B) is functional, but floating it dynamically based on where the heaviest cluster of arrows is on the field could prevent occasional overlap on the Matchup charts.
