# Research: Professional HTML Resume Templates (Open-Source)

> Resolves [#4](https://github.com/iaminfadel/flowjob/issues/4)

## Sources

- Web research on open-source HTML resume templates (2024–2026)
- GitHub repository analysis

## Candidate Templates

### 1. owengretzinger/html-resume-template ⭐ **RECOMMENDED**

- **Repo**: [github.com/owengretzinger/html-resume-template](https://github.com/owengretzinger/html-resume-template)
- **Tech**: HTML + Tailwind CSS
- **License**: Open source
- **ATS-friendly**: Yes — semantic HTML, standard headings
- **Print-ready**: Yes — Tailwind print modifiers, single-page PDF via browser print
- **Responsive**: Yes — two-column collapses on mobile
- **Customizable**: Highly — just HTML/CSS, easy to inject dynamic content

**Pros**:
- Clean, professional, corporate-appropriate design
- Built specifically for ATS compatibility
- Print CSS built in — renders to single-page PDF via Ctrl+P
- Detailed blog post explaining design philosophy
- Active maintenance

**Cons**:
- Uses Tailwind CSS — adds a build step (or CDN)
- For FlowJob, we'd need to extract the HTML structure and replace Tailwind with inline styles or vanilla CSS for Playwright PDF rendering

### 2. JSON Resume + Themes

- **Site**: [jsonresume.org](https://jsonresume.org)
- **Tech**: JSON schema → theme engine → HTML
- **License**: MIT
- **Themes**: 50+ community themes, many ATS-friendly

**Pros**:
- Standardized JSON schema — perfect for programmatic generation
- Separation of data and presentation
- Large theme ecosystem
- CLI tool for rendering

**Cons**:
- Adds a dependency (jsonresume CLI or theme packages)
- Theme quality varies widely
- Less control over fine-grained formatting

### 3. Reactive Resume (rxresu.me)

- **Site**: [rxresu.me](https://rxresu.me)
- **Tech**: Full application (React + PostgreSQL)
- **License**: MIT
- **Self-hostable**: Yes, via Docker

**Pros**:
- Feature-rich, AI-powered suggestions
- Multiple templates, all ATS-friendly
- Export to PDF built-in

**Cons**:
- **Way too heavy** for FlowJob — it's a full-stack app, not a template
- Would need to extract just the HTML template from their codebase
- Overkill dependency for our use case

## Recommendation

**Use owengretzinger/html-resume-template as the starting point**, but:

1. **Fork the HTML structure** — take the semantic HTML layout (sections, headings, lists)
2. **Replace Tailwind with vanilla CSS** — inline styles or a standalone CSS file. This eliminates the build step and gives us full control for Playwright PDF rendering.
3. **Templatize it** — use Python string templating (Jinja2) or simple string replacement to inject dynamic content from the Tailor agent's output.
4. **Add print CSS** — `@media print` rules for clean A4/Letter PDF output, page break control, margin tuning.

### ATS-Friendly Template Rules (from research)

- ✅ Single-column layout (or two-column that collapses cleanly)
- ✅ Semantic HTML: `<h1>` for name, `<h2>` for sections, `<ul>/<li>` for bullet points
- ✅ Standard section headings: "Work Experience", "Education", "Skills", "Projects"
- ✅ System-safe fonts (Arial, Calibri, Georgia, or Google Fonts that render as text)
- ✅ No tables, text boxes, or images for content
- ✅ No JavaScript for content rendering
- ✅ CSS units in `rem` or `cm` for print consistency
- ❌ No icons, infographics, or charts
- ❌ No headers/footers with critical info (ATS may skip them)
- ❌ No multi-column CSS grid for primary content (confuses parsers)
