/**
 * Rendering a questionnaire: the components, and the registry that swaps them.
 *
 * ```tsx
 * import { QuestionnaireView, registerWidget } from "vinta-django-questionnaires-client/widgets"
 * import "vinta-django-questionnaires-client/widgets.css"
 *
 * registerWidget("radio-group", MyRadioGroup)
 *
 * <QuestionnaireView plan={plan} answers={answers} onChange={setAnswer} />
 * ```
 *
 * Importing this module is what installs the defaults, so a host that only
 * wants the registry still gets a form that renders.
 */

// Side effect on purpose: the module body registers every default widget.
import "./defaults.js"

export {
  defaultWidgetKeys,
  CheckboxGroupWidget,
  FileWidget,
  ItemListWidget,
  MatrixWidget,
  MultiSelectWidget,
  NumberWidget,
  RadioGroupWidget,
  RangeWidget,
  RepeatableGroupWidget,
  SelectWidget,
  SubQuestionnaireWidget,
  TextAreaWidget,
  TextWidget,
} from "./defaults.js"
export {
  getWidget,
  isOverridden,
  registerDefaultWidget,
  registerWidget,
  registeredWidgetKeys,
  resetWidgetOverrides,
  resolveWidget,
  unregisterWidget,
  type WidgetComponent,
  type WidgetOption,
  type WidgetProps,
} from "./registry.js"
export {
  DEFAULT_COLUMN_COUNT,
  columnsFor,
  packRows,
  pageColumns,
  rangeForWidth,
  sectionColumns,
  spanOf,
  widthOf,
  type GridRow,
} from "./grid.js"
export {
  QuestionnaireView,
  QuestionView,
  type AnswerErrors,
  type Answers,
  type QuestionnaireViewProps,
  type QuestionViewProps,
  type ResolvedOptions,
} from "./QuestionnaireView.js"
export { planFromDefinition } from "../preview.js"
