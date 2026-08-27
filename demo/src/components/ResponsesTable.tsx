/**
 * Responses in a table, with the columns the reader picks.
 *
 * The interesting part is where the columns come from: nothing here knows what
 * the questionnaire asks. The server sends the column list alongside the rows,
 * TanStack Table is handed that list, and the picker toggles entries of it --
 * so a question added in the editor shows up here on the next load, and the
 * CSV export takes the same list, which is why the download matches the screen.
 *
 * Paging, filtering and sorting are the server's: a table of every response is
 * exactly the one that should not be fetched whole.
 */

import { useEffect, useMemo, useState } from "react"

import {
  cellText,
  groupColumns,
  type ResponseColumn,
  type ResponsePage,
  type ResponseQuery,
  type ResponseRow,
} from "@vintasoftware/django-questionnaires"
import {
  flexRender,
  getCoreRowModel,
  useReactTable,
  type ColumnDef,
} from "@tanstack/react-table"
import { Alert, AlertDescription, AlertTitle } from "vinta-schedule-design-system/ui/alert"
import { Badge } from "vinta-schedule-design-system/ui/badge"
import { Button } from "vinta-schedule-design-system/ui/button"
import { Card, CardContent } from "vinta-schedule-design-system/ui/card"
import { Checkbox } from "vinta-schedule-design-system/ui/checkbox"
import { Input } from "vinta-schedule-design-system/ui/input"
import { Label } from "vinta-schedule-design-system/ui/label"
import { Spinner } from "vinta-schedule-design-system/ui/spinner"
import { Container, HStack, PageHeader, Text, VStack } from "vinta-schedule-design-system/layout"
import { Link } from "@tanstack/react-router"

import { editorApi } from "../editorApi"

const STATUSES = [
  { value: "", label: "Any status" },
  { value: "in_progress", label: "In progress" },
  { value: "completed", label: "Completed" },
  { value: "abandoned", label: "Abandoned" },
]

export function ResponsesTable() {
  const [questionnaire, setQuestionnaire] = useState("")
  const [questionnaires, setQuestionnaires] = useState<{ key: string; name: string }[]>([])
  const [status, setStatus] = useState("")
  const [search, setSearch] = useState("")
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(25)
  const [visible, setVisible] = useState<string[] | null>(null)
  const [data, setData] = useState<ResponsePage | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [failure, setFailure] = useState<string | null>(null)

  useEffect(() => {
    editorApi
      .listQuestionnaires()
      .then((found) => {
        setQuestionnaires(found)
        if (!questionnaire && found[0]) setQuestionnaire(found[0].key)
      })
      .catch((cause: unknown) => setFailure(describe(cause)))
    // Only on mount: picking a questionnaire is what the user does after.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const query: ResponseQuery = useMemo(
    () => ({ questionnaire, status, search, page, pageSize }),
    [questionnaire, status, search, page, pageSize],
  )

  useEffect(() => {
    const controller = new AbortController()
    setIsLoading(true)
    setFailure(null)
    editorApi
      .listResponses(query, controller.signal)
      .then((payload) => {
        if (controller.signal.aborted) return
        setData(payload)
        // The first load decides what is on screen; after that the reader does.
        setVisible((current) => current ?? payload.defaultColumns)
      })
      .catch((cause: unknown) => {
        if (!controller.signal.aborted) setFailure(describe(cause))
      })
      .finally(() => {
        if (!controller.signal.aborted) setIsLoading(false)
      })
    return () => controller.abort()
  }, [query])

  // Switching questionnaire changes what the columns even are.
  useEffect(() => {
    setVisible(null)
    setPage(1)
  }, [questionnaire])

  const shown = useMemo(
    () => (data ? data.columns.filter((column) => (visible ?? []).includes(column.key)) : []),
    [data, visible],
  )

  const columns = useMemo<ColumnDef<ResponseRow>[]>(
    () =>
      shown.map((column) => ({
        id: column.key,
        header: column.label,
        accessorFn: (row) => row[column.key],
        cell: (info) => <Cell column={column} value={info.getValue()} />,
      })),
    [shown],
  )

  const table = useReactTable({
    data: data?.results ?? [],
    columns,
    getCoreRowModel: getCoreRowModel(),
    manualPagination: true,
    pageCount: data?.totalPages ?? 1,
  })

  return (
    <Container py={8}>
      <VStack gap={6}>
        <PageHeader
          title="Responses"
          description="Everything answered, with the columns you pick."
          actions={
            <HStack gap={2}>
              <Button variant="outline" asChild>
                <Link to="/editor">Editor</Link>
              </Button>
              <Button
                onClick={() => {
                  window.location.href = editorApi.responseExportUrl({
                    ...query,
                    columns: visible ?? undefined,
                  })
                }}
                disabled={!data?.total}
              >
                Export CSV
              </Button>
            </HStack>
          }
        />

        {failure ? (
          <Alert variant="destructive">
            <AlertTitle>Could not read the responses</AlertTitle>
            <AlertDescription>{failure}</AlertDescription>
          </Alert>
        ) : null}

        <Card>
          <CardContent>
            <VStack gap={4}>
              <HStack gap={3} wrap align="end">
                <VStack gap={1}>
                  <Label htmlFor="questionnaire">Questionnaire</Label>
                  <select
                    id="questionnaire"
                    className="demo-select"
                    value={questionnaire}
                    onChange={(event) => setQuestionnaire(event.target.value)}
                  >
                    <option value="">Every questionnaire</option>
                    {questionnaires.map((entry) => (
                      <option key={entry.key} value={entry.key}>
                        {entry.name}
                      </option>
                    ))}
                  </select>
                </VStack>
                <VStack gap={1}>
                  <Label htmlFor="status">Status</Label>
                  <select
                    id="status"
                    className="demo-select"
                    value={status}
                    onChange={(event) => {
                      setStatus(event.target.value)
                      setPage(1)
                    }}
                  >
                    {STATUSES.map((entry) => (
                      <option key={entry.value} value={entry.value}>
                        {entry.label}
                      </option>
                    ))}
                  </select>
                </VStack>
                <VStack gap={1}>
                  <Label htmlFor="search">Search</Label>
                  <Input
                    id="search"
                    placeholder="Respondent or external id"
                    value={search}
                    onChange={(event) => {
                      setSearch(event.target.value)
                      setPage(1)
                    }}
                  />
                </VStack>
              </HStack>

              {data ? (
                <ColumnPicker
                  columns={data.columns}
                  visible={visible ?? []}
                  onChange={setVisible}
                  onReset={() => setVisible(data.defaultColumns)}
                />
              ) : null}
            </VStack>
          </CardContent>
        </Card>

        {isLoading && !data ? (
          <HStack gap={3} align="center">
            <Spinner />
            <Text color="muted-foreground">Reading the responses…</Text>
          </HStack>
        ) : null}

        {data ? (
          <Card>
            <CardContent>
              <div className="demo-table-scroll">
                <table className="demo-table">
                  <thead>
                    {table.getHeaderGroups().map((group) => (
                      <tr key={group.id}>
                        {group.headers.map((header) => (
                          <th key={header.id} scope="col">
                            {header.isPlaceholder
                              ? null
                              : flexRender(
                                  header.column.columnDef.header,
                                  header.getContext(),
                                )}
                          </th>
                        ))}
                      </tr>
                    ))}
                  </thead>
                  <tbody>
                    {table.getRowModel().rows.map((row) => (
                      <tr key={row.id}>
                        {row.getVisibleCells().map((cell) => (
                          <td key={cell.id}>
                            {flexRender(cell.column.columnDef.cell, cell.getContext())}
                          </td>
                        ))}
                      </tr>
                    ))}
                    {!data.results.length ? (
                      <tr>
                        <td colSpan={Math.max(1, shown.length)}>
                          <Text color="muted-foreground">Nothing answered yet.</Text>
                        </td>
                      </tr>
                    ) : null}
                  </tbody>
                </table>
              </div>

              <HStack gap={3} align="center" justify="between" style={{ marginTop: "1rem" }}>
                <Text color="muted-foreground">
                  {data.total} response(s) · page {data.page} of {data.totalPages}
                </Text>
                <HStack gap={2} align="center">
                  <select
                    className="demo-select"
                    aria-label="Rows per page"
                    value={pageSize}
                    onChange={(event) => {
                      setPageSize(Number(event.target.value))
                      setPage(1)
                    }}
                  >
                    {[10, 25, 50, 100].map((size) => (
                      <option key={size} value={size}>
                        {size} per page
                      </option>
                    ))}
                  </select>
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={data.page <= 1}
                    onClick={() => setPage((current) => current - 1)}
                  >
                    Previous
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={data.page >= data.totalPages}
                    onClick={() => setPage((current) => current + 1)}
                  >
                    Next
                  </Button>
                </HStack>
              </HStack>
            </CardContent>
          </Card>
        ) : null}
      </VStack>
    </Container>
  )
}

function ColumnPicker({
  columns,
  visible,
  onChange,
  onReset,
}: {
  columns: ResponseColumn[]
  visible: string[]
  onChange: (keys: string[]) => void
  onReset: () => void
}) {
  const [isOpen, setIsOpen] = useState(false)
  const groups = useMemo(() => groupColumns(columns), [columns])

  const toggle = (key: string) =>
    onChange(
      visible.includes(key)
        ? visible.filter((entry) => entry !== key)
        : // Kept in the server's order rather than the click order, so the
          // table does not shuffle as boxes are ticked.
          columns.filter((column) => column.key === key || visible.includes(column.key)).map(
            (column) => column.key,
          ),
    )

  return (
    <VStack gap={2}>
      <HStack gap={2} align="center">
        <Button variant="outline" size="sm" onClick={() => setIsOpen((open) => !open)}>
          {isOpen ? "Hide columns" : "Choose columns"}
        </Button>
        <Badge variant="secondary">{visible.length} shown</Badge>
        <Button variant="ghost" size="sm" onClick={onReset}>
          Reset
        </Button>
      </HStack>

      {isOpen ? (
        <div className="demo-column-picker">
          {groups.map((group) => (
            <VStack gap={2} key={group.title}>
              <Text size="sm" weight="medium">
                {group.title}
              </Text>
              {group.columns.map((column) => (
                <HStack gap={2} align="center" key={column.key}>
                  <Checkbox
                    id={`column-${column.key}`}
                    checked={visible.includes(column.key)}
                    onCheckedChange={() => toggle(column.key)}
                  />
                  <Label htmlFor={`column-${column.key}`}>{column.label}</Label>
                </HStack>
              ))}
            </VStack>
          ))}
        </div>
      ) : null}
    </VStack>
  )
}

function Cell({ column, value }: { column: ResponseColumn; value: unknown }) {
  if (column.key === "status") {
    return <Badge variant={value === "completed" ? "default" : "secondary"}>{String(value)}</Badge>
  }
  const text = cellText(value)
  if (!text) return <Text color="muted-foreground">—</Text>
  return <span title={text}>{text.length > 80 ? `${text.slice(0, 80)}…` : text}</span>
}

function describe(cause: unknown): string {
  return cause instanceof Error ? cause.message : String(cause)
}
