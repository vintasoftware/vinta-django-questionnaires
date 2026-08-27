/**
 * The React questionnaire editor.
 *
 * Kept behind its own entry point so the rest of the package -- the Zod schemas
 * a respondent's browser builds from a plan -- stays free of React.
 *
 * ```tsx
 * import { QuestionnaireEditor } from "@vintasoftware/django-questionnaires/editor"
 * import { createEditorClient } from "@vintasoftware/django-questionnaires"
 * import "@vintasoftware/django-questionnaires/editor.css"
 * ```
 */

export { QuestionnaireEditor, type QuestionnaireEditorProps } from "./QuestionnaireEditor.js"
export {
  useQuestionnaireEditor,
  type QuestionnaireEditor as QuestionnaireEditorHandle,
  type UseQuestionnaireEditorOptions,
} from "./useQuestionnaireEditor.js"
export { Outline, type OutlineProps } from "./Outline.js"
export { PageForm, QuestionForm, SectionForm, VersionForm } from "./forms.js"
export { JsonField, SchemaForm, type SchemaFormProps } from "./SchemaForm.js"
export {
  Button,
  Checkbox,
  Errors,
  Field,
  NumberInput,
  Select,
  TextArea,
  TextInput,
  type CheckboxProps,
  type FieldProps,
  type NumberInputProps,
  type Option,
  type SelectProps,
  type TextInputProps,
} from "./fields.js"
