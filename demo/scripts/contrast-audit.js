/**
 * WCAG contrast audit for whatever is currently on screen.
 *
 * Paste it into the browser console on http://localhost:5273 and read the
 * result. Run it again on each state that matters -- a filled page, a page
 * with errors showing, the completed view -- because each renders text the
 * others do not.
 *
 *   { examined: 42, failures: [], lowest: [...] }
 *
 * How it works: for every element holding text, it resolves the computed
 * colour through a canvas -- which is what lets it read `oklch()`, the format
 * the design system's tokens compile to -- composites any translucent
 * background down to an opaque one, and compares the two by WCAG relative
 * luminance. The threshold is 4.5:1, or 3:1 for large text (>= 24px, or
 * >= 18.66px bold), per WCAG 2.1 AA.
 */
;(() => {
  const ctx = document.createElement("canvas").getContext("2d", { willReadFrequently: true })
  const cache = new Map()

  /** Resolve any CSS colour to sRGB by letting the browser paint it. */
  const toRgb = (color) => {
    if (cache.has(color)) return cache.get(color)
    ctx.clearRect(0, 0, 1, 1)
    ctx.fillStyle = "#000"
    ctx.fillStyle = color
    ctx.fillRect(0, 0, 1, 1)
    const [r, g, b, a] = ctx.getImageData(0, 0, 1, 1).data
    const resolved = { r, g, b, a: a / 255 }
    cache.set(color, resolved)
    return resolved
  }

  const luminance = ({ r, g, b }) => {
    const channel = (v) => {
      v /= 255
      return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4)
    }
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)
  }

  const over = (fg, bg) => ({
    r: fg.r * fg.a + bg.r * (1 - fg.a),
    g: fg.g * fg.a + bg.g * (1 - fg.a),
    b: fg.b * fg.a + bg.b * (1 - fg.a),
    a: 1,
  })

  /** The opaque colour actually behind an element. */
  const backgroundOf = (element) => {
    let node = element
    let stack = null
    while (node) {
      const colour = toRgb(getComputedStyle(node).backgroundColor)
      if (colour.a > 0) {
        stack = stack ? over(stack, colour) : colour
        if (stack.a >= 1) return stack
      }
      node = node.parentElement
    }
    return stack && stack.a >= 1 ? stack : { r: 255, g: 255, b: 255, a: 1 }
  }

  const contrast = (a, b) => {
    const first = luminance(a)
    const second = luminance(b)
    const [lighter, darker] = first > second ? [first, second] : [second, first]
    return (lighter + 0.05) / (darker + 0.05)
  }

  const rows = []
  for (const element of document.querySelectorAll("body *")) {
    const text = [...element.childNodes]
      .filter((node) => node.nodeType === Node.TEXT_NODE)
      .map((node) => node.textContent.trim())
      .join(" ")
      .trim()
    const placeholder =
      element.tagName === "INPUT" || element.tagName === "TEXTAREA" ? element.placeholder : ""
    if (!text && !placeholder) continue

    const style = getComputedStyle(element)
    if (style.visibility === "hidden" || style.display === "none" || Number(style.opacity) === 0)
      continue
    const box = element.getBoundingClientRect()
    if (!box.width || !box.height) continue

    const size = parseFloat(style.fontSize)
    const weight = Number(style.fontWeight) || 400
    const isLarge = size >= 24 || (size >= 18.66 && weight >= 700)
    const background = backgroundOf(element)
    const foreground = over(toRgb(style.color), background)

    rows.push({
      text: (text || `placeholder: ${placeholder}`).slice(0, 48),
      ratio: Math.round(contrast(foreground, background) * 100) / 100,
      need: isLarge ? 3 : 4.5,
      size,
      color: style.color,
    })
  }

  rows.sort((a, b) => a.ratio - b.ratio)
  const failures = rows.filter((row) => row.ratio < row.need)
  console.table(failures.length ? failures : rows.slice(0, 8))
  return { examined: rows.length, failures, lowest: rows.slice(0, 8) }
})()
