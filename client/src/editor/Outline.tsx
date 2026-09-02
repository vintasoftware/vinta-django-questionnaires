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
import { useStrings, type WithStrings } from "./strings.js"
import type { Translate } from "../strings.js"

export interface OutlineProps extends WithStrings {
  document: QuestionnaireDefinition
  selection: Selection
  issues: readonly DefinitionIssue[]
  dispatch: (action: EditorAction) => void
}

export function Outline({ document, selection, issues, dispatch, strings }: OutlineProps) {
  const t = useStrings(strings)
  const selected = pathOf(selection)
  const isSelected = (path: NodePath | null) =>
    path === null ? selection.kind === "version" : pathOf(path) === selected
  const reorder = (path: NodePath | null) => (from: number, to: number) =>
    dispatch({ type: "reorder", path, from, to })

  return (
    // Two elements, not one, and the split is load-bearing. The `nav` fills the
    // grid row so its surface reaches the bottom of the inspector beside it;
    // the inner element is the one that sticks. A single element cannot do
    // both -- something pinned needs slack to move within, which a full-height
    // element has none of, so the two demands would cancel out.
    <nav className="vqe-outline" aria-label={t("outline.label")}>
      <div className="vqe-outline__pane">
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
          label={t("outline.list.pages")}
          ids={document.pages.map((_page, index) => `page-${index}`)}
          names={document.pages.map(
            (page) => page.title || page.key || t("outline.untitled.page"),
          )}
          onReorder={reorder(null)}
        >
          <ol className="vqe-outline__list">
            {document.pages.map((page, pageIndex) => {
              const pagePath = { page: pageIndex }
              return (
                <SortableItem key={`page-${pageIndex}`} id={`page-${pageIndex}`}>
                  {(handle) => (
                    <li>
                      <Row
                        handle={handle}
                        t={t}
                        kind="page"
                        label={page.title || page.key}
                        badges={[
                          page.isSkippable ? t("outline.badge.skippable") : null,
                          page.condition ? t("outline.badge.conditional") : null,
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
                        label={t("outline.list.sections")}
                        ids={page.sections.map((_section, index) => `section-${index}`)}
                        names={page.sections.map(
                          (section) =>
                            section.title || section.key || t("outline.untitled.section"),
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
                                key={`section-${sectionIndex}`}
                                id={`section-${sectionIndex}`}
                              >
                                {(sectionHandle) => (
                                  <li>
                                    <Row
                                      handle={sectionHandle}
                                      t={t}
                                      kind="section"
                                      label={section.title || section.key}
                                      badges={[
                                        section.condition
                                          ? t("outline.badge.conditional")
                                          : null,
                                      ]}
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
                                      label={t("outline.list.questions")}
                                      ids={section.questions.map(
                                        (_question, index) => `question-${index}`,
                                      )}
                                      names={section.questions.map(
                                        (question) =>
                                          question.title ||
                                          question.key ||
                                          t("outline.untitled.question"),
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
                                              key={`question-${questionIndex}`}
                                              id={`question-${questionIndex}`}
                                            >
                                              {(questionHandle) => (
                                                <li>
                                                  <Row
                                                    handle={questionHandle}
                                                    t={t}
                                                    kind="question"
                                                    label={question.title || question.key}
                                                    badges={[
                                                      question.questionType,
                                                      question.condition
                                                        ? t("outline.badge.conditional")
                                                        : null,
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
                                                title: t("editor.new.question"),
                                              })
                                            }
                                          >
                                            {t("outline.add.question")}
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
                              onClick={() =>
                                dispatch({
                                  type: "insert",
                                  path: pagePath,
                                  title: t("editor.new.section"),
                                })
                              }
                            >
                              {t("outline.add.section")}
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

        <Button
          variant="quiet"
          onClick={() => dispatch({ type: "insert", path: null, title: t("editor.new.page") })}
        >
          {t("outline.add.page")}
        </Button>
      </div>
    </nav>
  )
}

function Row({
  handle,
  t,
  kind,
  label,
  badges,
  selected,
  flagged,
  onSelect,
  onRemove,
}: {
  handle: HandleProps
  t: Translate
  // Narrow, because each kind has a name and a delete title of its own in the
  // catalogue rather than a noun glued onto a sentence -- a composition that
  // only reads as English.
  kind: "page" | "section" | "question"
  label: string
  badges: (string | null)[]
  selected: boolean
  flagged: boolean
  onSelect: () => void
  onRemove: () => void
}) {
  const name = t(`outline.item.${kind}`, { label: label || t("outline.untitled") })
  return (
    <div className={`vqe-outline__row${selected ? " is-selected" : ""}`}>
      <DragHandle handle={handle} label={name} />
      <button type="button" className="vqe-outline__button" onClick={onSelect}>
        <span className="vqe-outline__title">
          {flagged ? (
            <span className="vqe-outline__flag" aria-label={t("outline.flag")}>
              !
            </span>
          ) : null}
          {label || t("outline.untitled")}
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
        <button type="button" title={t(`outline.delete.${kind}`)} onClick={onRemove}>
          ×
        </button>
      </span>
    </div>
  )
}
