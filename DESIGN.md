
# Design System Document: V-Legal


## 1. Overview & Creative North Star

**Creative North Star: "The Scholarly Archive"**



This design system is built to transform the dense, often overwhelming landscape of legal documentation into a premium, editorial experience. We are moving away from the "database" aesthetic of the early web and toward a "Document-First" philosophy. The objective is to recreate the tactile authority of a physical law book—specifically the Vietnamese Government Gazette—within a digital high-performance environment.



By prioritizing high information density through meticulous typography rather than UI decoration, the system achieves "Organic Authority." We break the standard "dashboard" template by using a dominant, centered document column flanked by asymmetrical, utilitarian toolsets. The result is a scholarly space that invites deep reading while maintaining the rapid-reference capabilities required by legal professionals.



---



## 2. Colors

The palette is rooted in the "Ivory & Ink" tradition. It avoids the clinical coldness of pure white (#FFFFFF) in favor of a sophisticated ivory to reduce eye strain during prolonged research sessions.



* **Background (`#FCFAEE`):** Our foundation. This off-white tone mimics premium aged paper.

* **On-Background / On-Surface (`#1B1C15`):** Deep charcoal, not pure black, to provide high contrast that remains soft on the eyes.

* **Primary (`#005481` / `primary-container: #076DA5`):** A deep "National Navy" used for functional wayfinding and high-level categorization.

* **Secondary (`#8B5000` / `secondary-container: #FF9800`):** A "Legal Gold" used sparingly for highlights, citations, or "Effective" status indicators.



### The "No-Line" Rule

To maintain an editorial feel, 1px solid borders are generally prohibited for sectioning. Use **Background Color Shifts** instead.

* **Nesting:** Place a `surface-container-low` (#F6F4E8) block inside a `surface` (#FCFAEE) background to define a new context.

* **The "Glass & Gradient" Rule:** For floating headers or mobile navigation, use a `surface` color with a 90% opacity and a `20px` backdrop-blur. This ensures the document text is visible as it scrolls beneath, maintaining the "physical paper" layers.



---



## 3. Typography

Typography is the core of this system. We use **Noto Serif** to provide the necessary weight and authority for legal text, while **Work Sans** handles the utilitarian "metadata" and UI labels.



* **Display (Noto Serif):** Used for document titles and major legal acts. Large, centered, and authoritative.

* **Headline (Noto Serif):** Mimics the structure of official decrees. Bold, high-contrast, and strictly hierarchical.

* **Body (Noto Serif):** The workhorse. Set with generous line-height (`1.6`) to ensure legibility across dense clauses.

* **Label (Work Sans):** Used for "Clause" numbers, "Article" tags, and dates. These are the "marginalia" of our digital book.



**Hierarchy as Identity:**

By strictly separating "The Law" (Serif) from "The Interface" (Sans), we signal to the user exactly what is content and what is tool.



---



## 4. Elevation & Depth

In a scholarly environment, heavy drop shadows feel "app-like" and distracting. We use **Tonal Layering** to convey hierarchy.



* **The Layering Principle:** Depth is achieved by "stacking." A search bar or a "Quick Reference" card should be `surface-container-lowest` (#FFFFFF) sitting on a `surface-container` (#F0EEE2) section. This creates a soft, natural lift.

* **Ambient Shadows:** If a floating action button (e.g., "Export PDF") is required, use a shadow with a `24px` blur at `6%` opacity, tinted with the `on-surface` color.

* **The "Ghost Border" Fallback:** For secondary inputs or grid cells where separation is critical, use the `outline-variant` token at **15% opacity**. This creates a "suggestion" of a line rather than a hard boundary.



---



## 5. Components



### Document Layout (The Center Column)

The primary container is a centered column with a max-width of `800px`. This mimics the width of an A4 page, optimizing the measure (characters per line) for legal reading.



### Buttons

* **Primary:** Solid `primary` (#005481) with `on-primary` (#FFFFFF) text. Rectangular (0px radius) to maintain a structural, architectural feel.

* **Secondary/Ghost:** `outline` token at low opacity with Serif text. These should feel like "stamps" on the page.



### Chips (Legal Metadata)

* **Status Chips:** Use `secondary-container` for "Active" and `error-container` for "Expired." Text must be `label-sm` (Work Sans) to differentiate from document text.



### Input Fields

* **Style:** Minimalist. Only a bottom border (using `outline-variant`) that thickens to 2px of `primary` on focus. No rounded corners.



### Lists & Citations

* **Rule:** Forbid the use of horizontal divider lines between list items. Use the **Spacing Scale (Step 4: 0.9rem)** to create clear separation through whitespace. If items are extremely dense, use alternating `surface` and `surface-container-low` background fills (zebra striping) at very low contrast.



### Specialized Component: The "Article" Card

A layout block specifically for legal articles. It uses a `surface-container-highest` side-border (4px wide) on the left to indicate the start of a new clause, replacing the need for a full box enclosure.



---



## 6. Do's and Don'ts



### Do:

* **Do** use asymmetrical margins. A wider left margin allows for "Article" numbers to sit outside the main text flow, just like a printed gazette.

* **Do** use Noto Serif for all content that would be found in a physical law book.

* **Do** prioritize vertical rhythm. Ensure all spacing follows the `0.2rem` (Step 1) increments.



### Don't:

* **Don't** use `0px` shadows that are 100% black. They break the scholarly, ivory-toned atmosphere.

* **Don't** use rounded corners. This design system is built on the "Power of the Rectangle"—sharp, precise, and official.

* **Don't** use bright, saturated blues or greens. Stick to the muted, professional tones defined in the palette to maintain "National Authority."

* **Don't** use icons for primary navigation without accompanying text labels. Legal users value precision over abstract symbols.



---



## 7. Spacing & Grid

The system uses a **Baseline Grid of 4px**.

* **Document Padding:** `spacing.16` (3.5rem) on desktop to create a "Marginal" feel.

* **Information Density:** In the sidebar/navigation, use `spacing.2` (0.4rem) to allow for high-density links and cross-references.

* **Content Breathing Room:** Between Articles, use `spacing.10` (2.25rem) to signify a clear change in subject matter.```