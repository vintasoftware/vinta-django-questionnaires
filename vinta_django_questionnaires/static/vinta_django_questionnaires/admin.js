/*
 * Reordering on the structure editor, and keeping clicks off the disclosures.
 *
 * The `order` field is what the server sorts by, so a drag does two things:
 * moves the node in the DOM, and rewrites the order inputs of everything in
 * that list to match. Nothing is posted until Save, which is the same as every
 * other change on the page.
 *
 * Plain drag-and-drop rather than a library, because this is a Django app and
 * shipping a bundler for one interaction is not a trade worth making. The
 * keyboard path is separate and simpler: focus a grip and use the arrow keys.
 */
;(() => {
  "use strict"

  const NODE = "[data-vqa-sortable] > .vqa-node, [data-vqa-sortable] > .vqa-item"

  /** The sortable list a node belongs to, and its siblings in order. */
  const siblingsOf = (node) => {
    const list = node.parentElement
    return [...list.children].filter((child) => child.matches(".vqa-node, .vqa-item"))
  }

  /** Rewrite every order input of a list to match the order on screen. */
  const renumber = (node) => {
    siblingsOf(node).forEach((sibling, index) => {
      const input = sibling.querySelector("input.vqa-order")
      if (input) input.value = String(index)
    })
  }

  const move = (node, by) => {
    const siblings = siblingsOf(node)
    const from = siblings.indexOf(node)
    const to = from + by
    if (to < 0 || to >= siblings.length) return
    const list = node.parentElement
    if (by < 0) list.insertBefore(node, siblings[to])
    else list.insertBefore(node, siblings[to].nextSibling)
    renumber(node)
    node.querySelector("[data-vqa-handle]")?.focus()
  }

  document.addEventListener("DOMContentLoaded", () => {
    // A click on an input inside a <summary> would otherwise toggle it, which
    // makes typing in the key field close the node you are editing.
    document.querySelectorAll("[data-vqa-stop]").forEach((element) => {
      element.addEventListener("click", (event) => {
        if (event.target.closest("input, select, textarea, label")) event.stopPropagation()
      })
    })

    document.querySelectorAll("[data-vqa-handle]").forEach((handle) => {
      const node = handle.closest(".vqa-node, .vqa-item")
      if (!node) return

      handle.setAttribute("tabindex", "0")
      handle.setAttribute("role", "button")
      // The label comes from the template, which is where a translation can
      // reach it -- this file is served as a static asset, not rendered.
      handle.setAttribute(
        "aria-label",
        handle.getAttribute("data-vqa-handle") ||
          handle.getAttribute("title") ||
          "Reorder, with the arrow keys",
      )
      node.setAttribute("draggable", "true")

      handle.addEventListener("keydown", (event) => {
        if (event.key === "ArrowUp") {
          event.preventDefault()
          move(node, -1)
        } else if (event.key === "ArrowDown") {
          event.preventDefault()
          move(node, 1)
        }
      })

      node.addEventListener("dragstart", (event) => {
        // Only a drag that began on the grip counts, so selecting text in a
        // field does not pick the whole question up.
        if (!event.target.closest("[data-vqa-handle]")) {
          event.preventDefault()
          return
        }
        node.classList.add("vqa-dragging")
        event.dataTransfer.effectAllowed = "move"
        event.dataTransfer.setData("text/plain", "")
      })

      node.addEventListener("dragend", () => {
        node.classList.remove("vqa-dragging")
        renumber(node)
      })
    })

    document.querySelectorAll("[data-vqa-sortable]").forEach((list) => {
      list.addEventListener("dragover", (event) => {
        const dragging = document.querySelector(".vqa-dragging")
        // A node only moves within the list it started in: taking a question
        // out of its section is not a change this tree has a shape for.
        if (!dragging || dragging.parentElement !== list) return
        event.preventDefault()
        const after = [...list.querySelectorAll(NODE)]
          .filter((node) => node !== dragging && node.parentElement === list)
          .find((node) => {
            const box = node.getBoundingClientRect()
            return event.clientY < box.top + box.height / 2
          })
        if (after) list.insertBefore(dragging, after)
        else list.appendChild(dragging)
      })
    })
  })
})()
