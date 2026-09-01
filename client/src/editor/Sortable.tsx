/**
 * Drag to reorder, one list at a time.
 *
 * There is a `DndContext` per list rather than one for the whole editor, which
 * is what makes a drag unable to take a question out of its section or a page
 * into another page: those are moves the questionnaire's shape does not have,
 * and the cheapest way to make them impossible is not to model them.
 *
 * dnd-kit's keyboard sensor comes with it, so every list is reorderable from
 * the keyboard: tab to a handle, space to lift, arrows to move, space to drop.
 */

import {
  DndContext,
  KeyboardSensor,
  PointerSensor,
  closestCenter,
  useSensor,
  useSensors,
  type DragEndEvent,
} from "@dnd-kit/core"
import { restrictToParentElement, restrictToVerticalAxis } from "@dnd-kit/modifiers"
import {
  SortableContext,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from "@dnd-kit/sortable"
import { CSS } from "@dnd-kit/utilities"
import type { ReactNode } from "react"

export interface SortableListProps {
  /**
   * One per item, stable across renders and unique within this list. Derive
   * them from the item's position, not from its editable content: these ids
   * are the React keys too, so an id that changes as a field is typed in
   * remounts the row and drops the focus.
   */
  ids: string[]
  /**
   * What to call each item when a drag is announced, one per id. Without it
   * the announcement falls back to the id, which is positional and says
   * nothing to whoever is listening.
   */
  names?: string[]
  onReorder: (from: number, to: number) => void
  children: ReactNode
  /** Announced when a drag starts, for anyone listening rather than looking. */
  label?: string
}

export function SortableList({ ids, names, onReorder, children, label }: SortableListProps) {
  const sensors = useSensors(
    // A few pixels of travel before a drag starts, so clicking a row to select
    // it does not turn into a drag.
    useSensor(PointerSensor, { activationConstraint: { distance: 4 } }),
    useSensor(KeyboardSensor, {
      coordinateGetter: sortableKeyboardCoordinates,
    }),
  )

  const nameOf = (id: string | number) => {
    const index = ids.indexOf(String(id))
    return names?.[index] || String(id)
  }

  const handleEnd = (event: DragEndEvent) => {
    const { active, over } = event
    if (!over || active.id === over.id) return
    const from = ids.indexOf(String(active.id))
    const to = ids.indexOf(String(over.id))
    if (from === -1 || to === -1) return
    onReorder(from, to)
  }

  return (
    <DndContext
      sensors={sensors}
      collisionDetection={closestCenter}
      modifiers={[restrictToVerticalAxis, restrictToParentElement]}
      onDragEnd={handleEnd}
      accessibility={label ? { announcements: announcementsFor(label, nameOf) } : undefined}
    >
      <SortableContext items={ids} strategy={verticalListSortingStrategy}>
        {children}
      </SortableContext>
    </DndContext>
  )
}

export interface SortableItemProps {
  id: string
  /** Rendered with the handle's props, so the handle can be anywhere inside. */
  children: (handle: HandleProps) => ReactNode
  className?: string
}

export interface HandleProps {
  attributes: Record<string, unknown>
  listeners: Record<string, unknown>
  isDragging: boolean
}

export function SortableItem({ id, children, className }: SortableItemProps) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id,
  })
  return (
    <div
      ref={setNodeRef}
      className={`${className ?? ""}${isDragging ? " is-dragging" : ""}`.trim()}
      style={{
        transform: CSS.Transform.toString(transform),
        transition,
        // Lifted above its neighbours, so it is visible over the row it is
        // passing rather than under it.
        zIndex: isDragging ? 1 : undefined,
        position: isDragging ? "relative" : undefined,
      }}
    >
      {children({
        attributes: attributes as unknown as Record<string, unknown>,
        listeners: (listeners ?? {}) as unknown as Record<string, unknown>,
        isDragging,
      })}
    </div>
  )
}

/** The grip. Everything draggable gets one, and nothing else drags. */
export function DragHandle({ handle, label }: { handle: HandleProps; label: string }) {
  return (
    <button
      type="button"
      className="vqe-handle"
      aria-label={`Reorder ${label}`}
      title={`Drag to reorder ${label}`}
      {...handle.attributes}
      {...handle.listeners}
    >
      <span aria-hidden="true">⠿</span>
    </button>
  )
}

function announcementsFor(label: string, nameOf: (id: string | number) => string) {
  return {
    onDragStart: ({ active }: { active: { id: string | number } }) =>
      `Picked up ${nameOf(active.id)} in ${label}. Use the arrow keys to move it, space to drop it.`,
    onDragOver: () => undefined,
    onDragEnd: ({ active }: { active: { id: string | number } }) =>
      `Dropped ${nameOf(active.id)}.`,
    onDragCancel: ({ active }: { active: { id: string | number } }) =>
      `Left ${nameOf(active.id)} where it was.`,
  }
}
