/**
 * The tree down the left: pages, their sections, their questions.
 *
 * It is the editor's navigation and its map at the same time, so it says more
 * than the titles: which nodes carry a condition, which page can be skipped,
 * and which branch has something wrong under it.
 *
 * Each level is its own sortable list, so a drag reorders within a section, a
 * page or the questionnaire -- and cannot move a question into a different
 * section, which is a change the tree does not have a shape for.
 */

import type { DefinitionIssue, QuestionnaireDefinition } from "../definition.js"
import {
  hasIssuesUnder,
  pathOf,
  type EditorAction,
  type NodePath,
  type Selection,
} from "../editorState.js"
import { DragHandle, SortableItem, SortableList, type HandleProps } from "./Sortable.js"
import { Button } from "./fields.js"

export interface OutlineProps {
  document: QuestionnaireDefinition
  selection: Selection
  issues: readonly DefinitionIssue[]
  dispatch: (action: EditorAction) => void
}

export function Outline({ document, selection, issues, dispatch }: OutlineProps) {
  const selected = pathOf(selection)
  const isSelected = (path: NodePath | null) =>
    path === null ? selection.kind === "version" : pathOf(path) === selected
  const reorder = (path: NodePath | null) => (from: number, to: number) =>
    dispatch({ type: "reorder", path, from, to })

  return (
    <nav className="vqe-outline" aria-label="Questionnaire outline">
      <button
        type="button"
        className={`vqe-outline__row vqe-outline__row--version${
          isSelected(null) ? " is-selected" : ""
        }`}
        onClick={() => dispatch({ type: "select", selection: { kind: "version" } })}
      >
        <span className="vqe-outline__title">
          {document.title || document.questionnaire.key}
        </span>
        <span className="vqe-outline__meta">v{document.version}</span>
      </button>

      <SortableList
        label="pages"
        ids={document.pages.map((page, index) => page.key || `page-${index}`)}
        onReorder={reorder(null)}
      >
        <ol className="vqe-outline__list">
          {document.pages.map((page, pageIndex) => {
            const pagePath = { page: pageIndex }
            return (
              <SortableItem key={page.key || pageIndex} id={page.key || `page-${pageIndex}`}>
                {(handle) => (
                  <li>
                    <Row
                      handle={handle}
                      kind="page"
                      label={page.title || page.key}
                      badges={[
                        page.isSkippable ? "skippable" : null,
                        page.condition ? "conditional" : null,
                      ]}
                      selected={isSelected(pagePath)}
                      flagged={hasIssuesUnder(issues, pathOf(pagePath))}
                      onSelect={() =>
                        dispatch({
                          type: "select",
                          selection: { kind: "page", ...pagePath },
                        })
                      }
                      onRemove={() => dispatch({ type: "remove", path: pagePath })}
                    />
                    <SortableList
                      label="sections"
                      ids={page.sections.map(
                        (section, index) => section.key || `section-${index}`,
                      )}
                      onReorder={reorder(pagePath)}
                    >
                      <ol className="vqe-outline__list vqe-outline__list--nested">
                        {page.sections.map((section, sectionIndex) => {
                          const sectionPath = {
                            page: pageIndex,
                            section: sectionIndex,
                          }
                          return (
                            <SortableItem
                              key={section.key || sectionIndex}
                              id={section.key || `section-${sectionIndex}`}
                            >
                              {(sectionHandle) => (
                                <li>
                                  <Row
                                    handle={sectionHandle}
                                    kind="section"
                                    label={section.title || section.key}
                                    badges={[section.condition ? "conditional" : null]}
                                    selected={isSelected(sectionPath)}
                                    flagged={hasIssuesUnder(issues, pathOf(sectionPath))}
                                    onSelect={() =>
                                      dispatch({
                                        type: "select",
                                        selection: {
                                          kind: "section",
                                          ...sectionPath,
                                        },
                                      })
                                    }
                                    onRemove={() =>
                                      dispatch({
                                        type: "remove",
                                        path: sectionPath,
                                      })
                                    }
                                  />
                                  <SortableList
                                    label="questions"
                                    ids={section.questions.map(
                                      (question, index) => question.key || `question-${index}`,
                                    )}
                                    onReorder={reorder(sectionPath)}
                                  >
                                    <ol className="vqe-outline__list vqe-outline__list--nested">
                                      {section.questions.map((question, questionIndex) => {
                                        const questionPath = {
                                          page: pageIndex,
                                          section: sectionIndex,
                                          question: questionIndex,
                                        }
                                        return (
                                          <SortableItem
                                            key={question.key || questionIndex}
                                            id={question.key || `question-${questionIndex}`}
                                          >
                                            {(questionHandle) => (
                                              <li>
                                                <Row
                                                  handle={questionHandle}
                                                  kind="question"
                                                  label={question.title || question.key}
                                                  badges={[
                                                    question.questionType,
                                                    question.condition ? "conditional" : null,
                                                  ]}
                                                  selected={isSelected(questionPath)}
                                                  flagged={hasIssuesUnder(
                                                    issues,
                                                    pathOf(questionPath),
                                                  )}
                                                  onSelect={() =>
                                                    dispatch({
                                                      type: "select",
                                                      selection: {
                                                        kind: "question",
                                                        ...questionPath,
                                                      },
                                                    })
                                                  }
                                                  onRemove={() =>
                                                    dispatch({
                                                      type: "remove",
                                                      path: questionPath,
                                                    })
                                                  }
                                                />
                                              </li>
                                            )}
                                          </SortableItem>
                                        )
                                      })}
                                      <li>
                                        <Button
                                          variant="quiet"
                                          onClick={() =>
                                            dispatch({
                                              type: "insert",
                                              path: sectionPath,
                                            })
                                          }
                                        >
                                          + Question
                                        </Button>
                                      </li>
                                    </ol>
                                  </SortableList>
                                </li>
                              )}
                            </SortableItem>
                          )
                        })}
                        <li>
                          <Button
                            variant="quiet"
                            onClick={() => dispatch({ type: "insert", path: pagePath })}
                          >
                            + Section
                          </Button>
                        </li>
                      </ol>
                    </SortableList>
                  </li>
                )}
              </SortableItem>
            )
          })}
        </ol>
      </SortableList>

      <Button variant="quiet" onClick={() => dispatch({ type: "insert", path: null })}>
        + Page
      </Button>
    </nav>
  )
}

function Row({
  handle,
  kind,
  label,
  badges,
  selected,
  flagged,
  onSelect,
  onRemove,
}: {
  handle: HandleProps
  kind: string
  label: string
  badges: (string | null)[]
  selected: boolean
  flagged: boolean
  onSelect: () => void
  onRemove: () => void
}) {
  return (
    <div className={`vqe-outline__row${selected ? " is-selected" : ""}`}>
      <DragHandle handle={handle} label={`${kind} ${label || "untitled"}`} />
      <button type="button" className="vqe-outline__button" onClick={onSelect}>
        <span className="vqe-outline__title">
          {flagged ? (
            <span className="vqe-outline__flag" aria-label="Has a problem">
              !
            </span>
          ) : null}
          {label || "Untitled"}
        </span>
        <span className="vqe-outline__badges">
          {badges.filter(Boolean).map((badge) => (
            <span className="vqe-badge" key={badge}>
              {badge}
            </span>
          ))}
        </span>
      </button>
      <span className="vqe-outline__controls">
        <button type="button" title={`Delete this ${kind}`} onClick={onRemove}>
          ×
        </button>
      </span>
    </div>
  )
}
