'use client'

import { useState, useEffect } from 'react'
import axios from 'axios'

const LAST_SUCCESS_STORAGE_KEY = 'pdfPipeline:lastSuccess'

type ProcessMode = 'full' | 'tables_only'

interface ProcessingResult {
  job_id: string
  status: string
  mode?: ProcessMode
  result?: any
  downloads?: {
    normalized_text?: string
    clauses_json?: string
    tables_json?: string
  }
}

/** Max upload size (bytes); keep reasonable for local processing */
const MAX_PDF_BYTES = 85 * 1024 * 1024
const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000'

function buildApiUrl(path: string): string {
  return `${API_BASE_URL}${path}`
}

/** Browser waits for one HTTP response; large PDFs can take 30–60+ minutes. */
const PROCESS_REQUEST_TIMEOUT_MS = 3 * 60 * 60 * 1000 // 3 hours

function formatProcessingError(err: unknown): string {
  if (axios.isAxiosError(err)) {
    const detail = err.response?.data?.detail
    if (typeof detail === 'string' && detail.trim()) {
      return detail
    }
    if (err.code === 'ECONNABORTED' || err.message?.toLowerCase().includes('timeout')) {
      return (
        'Request timed out before the server finished. Very large PDFs can take an hour or more. ' +
        'Increase wait time or run processing on the backend only; the job may still complete on the server.'
      )
    }
    if (
      err.code === 'ERR_NETWORK' ||
      err.code === 'ECONNRESET' ||
      err.message?.includes('Network Error')
    ) {
      return (
        'Connection to the server was lost before the response arrived. ' +
        'This often happens with large uploads or long runs. Check that the backend is still running; processing may have completed anyway.'
      )
    }
  }
  return 'Error processing PDF. Please try again.'
}

function validatePdfFile(f: File): string | null {
  if (f.type !== 'application/pdf') {
    return 'Please upload a PDF file'
  }
  if (f.size > MAX_PDF_BYTES) {
    return 'PDF must be 85MB or smaller'
  }
  return null
}

export default function Home() {
  const [file, setFile] = useState<File | null>(null)
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<ProcessingResult | null>(null)
  const [lastSuccess, setLastSuccess] = useState<ProcessingResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [dragActive, setDragActive] = useState(false)
  const [processMode, setProcessMode] = useState<ProcessMode>('full')

  useEffect(() => {
    try {
      const raw = sessionStorage.getItem(LAST_SUCCESS_STORAGE_KEY)
      if (!raw) return
      const parsed = JSON.parse(raw) as ProcessingResult
      if (parsed?.status === 'success' && parsed.job_id && parsed.downloads) {
        setLastSuccess(parsed)
      }
    } catch {
      sessionStorage.removeItem(LAST_SUCCESS_STORAGE_KEY)
    }
  }, [])

  const displayResult: ProcessingResult | null =
    result?.status === 'success' && result.downloads
      ? result
      : lastSuccess?.status === 'success' && lastSuccess.downloads
        ? lastSuccess
        : null

  const dismissSavedResults = () => {
    sessionStorage.removeItem(LAST_SUCCESS_STORAGE_KEY)
    setLastSuccess(null)
  }

  const handleDrag = (e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    if (e.type === 'dragenter' || e.type === 'dragover') {
      setDragActive(true)
    } else if (e.type === 'dragleave') {
      setDragActive(false)
    }
  }

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    setDragActive(false)

    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      const droppedFile = e.dataTransfer.files[0]
      const err = validatePdfFile(droppedFile)
      if (err) {
        setError(err)
        setFile(null)
      } else {
        setFile(droppedFile)
        setError(null)
      }
    }
  }

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      const selectedFile = e.target.files[0]
      const err = validatePdfFile(selectedFile)
      if (err) {
        setError(err)
        setFile(null)
      } else {
        setFile(selectedFile)
        setError(null)
      }
    }
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!file) {
      setError('Please select a PDF file')
      return
    }
    const pre = validatePdfFile(file)
    if (pre) {
      setError(pre)
      return
    }

    setLoading(true)
    setError(null)
    setResult(null)

    try {
      const formData = new FormData()
      formData.append('file', file)

      const endpoint =
        processMode === 'tables_only' ? '/api/process-pdf-tables' : '/api/process-pdf'

      const response = await axios.post(buildApiUrl(endpoint), formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
        timeout: PROCESS_REQUEST_TIMEOUT_MS,
      })

      setResult(response.data)
      if (response.data?.status === 'success' && response.data?.job_id) {
        try {
          sessionStorage.setItem(LAST_SUCCESS_STORAGE_KEY, JSON.stringify(response.data))
          setLastSuccess(response.data)
        } catch {
          /* ignore quota / private mode */
        }
      }
    } catch (err: any) {
      console.error('Processing error:', err)
      setError(formatProcessingError(err))
    } finally {
      setLoading(false)
    }
  }

  const handleDownload = (url: string, filename: string) => {
    const resolvedUrl = url.startsWith('/') ? buildApiUrl(url) : url
    window.open(resolvedUrl, '_blank')
  }

  return (
    <main className="min-h-screen bg-gradient-to-b from-slate-50 to-slate-100">
      {/* Header */}
      <div className="bg-white border-b border-slate-200">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
          <h1 className="text-3xl font-bold text-slate-900">
            PDF Structure Extraction Pipeline
          </h1>
          <p className="mt-2 text-slate-600">
            Extract structured text, clauses, and tables from PDF documents
          </p>
        </div>
      </div>

      <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
        {/* Upload Form */}
        <div className="bg-white rounded-lg shadow-sm border border-slate-200 p-8 mb-8">
          <h2 className="text-xl font-semibold text-slate-900 mb-6">Upload PDF Document</h2>
          
          <form onSubmit={handleSubmit}>
            {/* Drag and Drop Area */}
            <div
              className={`relative border-2 border-dashed rounded-lg p-12 text-center transition-colors ${
                dragActive
                  ? 'border-blue-500 bg-blue-50'
                  : 'border-slate-300 bg-slate-50 hover:border-slate-400'
              }`}
              onDragEnter={handleDrag}
              onDragLeave={handleDrag}
              onDragOver={handleDrag}
              onDrop={handleDrop}
            >
              <input
                type="file"
                id="file-upload"
                accept=".pdf"
                onChange={handleFileChange}
                className="hidden"
              />
              
              <label
                htmlFor="file-upload"
                className="cursor-pointer"
              >
                <div className="space-y-4">
                  <div className="flex justify-center">
                    <svg
                      className="w-16 h-16 text-slate-400"
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={1.5}
                        d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"
                      />
                    </svg>
                  </div>
                  
                  <div>
                    <p className="text-lg text-slate-600">
                      <span className="font-semibold text-blue-600">Click to upload</span> or drag and drop
                    </p>
                    <p className="text-sm text-slate-500 mt-1">PDF files only (max 85MB)</p>
                    <p className="text-xs text-slate-400 mt-2 max-w-md mx-auto">
                      Large documents may take a long time to process. Keep this tab open; the browser waits for the full result (up to 3 hours).
                    </p>
                  </div>
                  
                  {file && (
                    <div className="mt-4 p-4 bg-blue-50 border border-blue-200 rounded-lg">
                      <p className="text-sm font-medium text-blue-900">
                        Selected: {file.name}
                      </p>
                      <p className="text-xs text-blue-700 mt-1">
                        {(file.size / 1024 / 1024).toFixed(2)} MB
                      </p>
                    </div>
                  )}
                </div>
              </label>
            </div>

            {/* Error Message */}
            {error && (
              <div className="mt-4 p-4 bg-red-50 border border-red-200 rounded-lg">
                <p className="text-sm text-red-800">{error}</p>
              </div>
            )}

            {/* Run mode */}
            <fieldset className="mt-6 space-y-3">
              <legend className="text-sm font-medium text-slate-800 mb-2">Run mode</legend>
              <label className="flex items-start gap-3 cursor-pointer rounded-lg border border-slate-200 bg-white p-3 hover:bg-slate-50">
                <input
                  type="radio"
                  name="processMode"
                  value="full"
                  checked={processMode === 'full'}
                  onChange={() => setProcessMode('full')}
                  className="mt-1"
                />
                <span>
                  <span className="font-medium text-slate-900">Full pipeline</span>
                  <span className="block text-xs text-slate-600 mt-0.5">
                    Clauses, tables, normalized text, and validation (slowest on large PDFs).
                  </span>
                </span>
              </label>
              <label className="flex items-start gap-3 cursor-pointer rounded-lg border border-emerald-200 bg-emerald-50/40 p-3 hover:bg-emerald-50/70">
                <input
                  type="radio"
                  name="processMode"
                  value="tables_only"
                  checked={processMode === 'tables_only'}
                  onChange={() => setProcessMode('tables_only')}
                  className="mt-1"
                />
                <span>
                  <span className="font-medium text-slate-900">Tables only</span>
                  <span className="block text-xs text-slate-600 mt-0.5">
                    Writes only <code className="text-emerald-900 bg-emerald-100/80 px-1 rounded">tables.json</code> under
                    the job folder—much faster for iterating on table extraction. Parent clause links are not filled.
                  </span>
                </span>
              </label>
            </fieldset>

            {/* Submit Button */}
            <button
              type="submit"
              disabled={!file || loading}
              className={`mt-6 w-full py-3 px-6 rounded-lg font-medium text-white transition-colors ${
                !file || loading
                  ? 'bg-slate-400 cursor-not-allowed'
                  : processMode === 'tables_only'
                    ? 'bg-emerald-600 hover:bg-emerald-700'
                    : 'bg-blue-600 hover:bg-blue-700'
              }`}
            >
              {loading ? (
                <span className="flex items-center justify-center">
                  <svg
                    className="animate-spin -ml-1 mr-3 h-5 w-5 text-white"
                    fill="none"
                    viewBox="0 0 24 24"
                  >
                    <circle
                      className="opacity-25"
                      cx="12"
                      cy="12"
                      r="10"
                      stroke="currentColor"
                      strokeWidth="4"
                    />
                    <path
                      className="opacity-75"
                      fill="currentColor"
                      d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                    />
                  </svg>
                  {processMode === 'tables_only' ? 'Extracting tables…' : 'Processing PDF…'}
                </span>
              ) : processMode === 'tables_only' ? (
                'Extract tables only'
              ) : (
                'Process PDF'
              )}
            </button>
          </form>
        </div>

        {/* Results: current run or last successful run (sessionStorage) */}
        {displayResult && (
          <div className="bg-white rounded-lg shadow-sm border border-slate-200 p-8">
            <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3 mb-6">
              <div>
                <h2 className="text-xl font-semibold text-slate-900">Processing Complete</h2>
                {displayResult.mode === 'tables_only' && (
                  <p className="mt-1 text-sm text-emerald-800 font-medium">
                    Tables-only run — download <span className="font-mono">tables.json</span> below.
                  </p>
                )}
              </div>
              {!result && lastSuccess && (
                <div className="flex flex-col sm:items-end gap-2 text-sm">
                  <p className="text-amber-800 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2">
                    Showing downloads from your last successful run in this browser tab (e.g. after refresh or if the
                    latest request did not return JSON).
                  </p>
                  <button
                    type="button"
                    onClick={dismissSavedResults}
                    className="text-slate-600 underline hover:text-slate-900"
                  >
                    Dismiss saved results
                  </button>
                </div>
              )}
            </div>
            <p className="text-xs text-slate-500 mb-6 font-mono break-all">
              Job ID: {displayResult.job_id}
            </p>
            
            {/* Summary */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-8">
              <div
                className={`p-4 rounded-lg border ${
                  displayResult.mode === 'tables_only'
                    ? 'bg-slate-100 border-slate-200 opacity-80'
                    : 'bg-blue-50 border-blue-200'
                }`}
              >
                <p
                  className={`text-sm font-medium ${
                    displayResult.mode === 'tables_only' ? 'text-slate-600' : 'text-blue-900'
                  }`}
                >
                  Clauses Extracted
                </p>
                <p
                  className={`text-2xl font-bold mt-1 ${
                    displayResult.mode === 'tables_only' ? 'text-slate-500' : 'text-blue-600'
                  }`}
                >
                  {displayResult.result?.summary?.total_clauses ?? 0}
                </p>
                {displayResult.mode === 'tables_only' && (
                  <p className="text-xs text-slate-500 mt-1">Not run in tables-only mode</p>
                )}
              </div>
              
              <div className="p-4 bg-green-50 rounded-lg border border-green-200">
                <p className="text-sm font-medium text-green-900">Tables Extracted</p>
                <p className="text-2xl font-bold text-green-600 mt-1">
                  {displayResult.result?.summary?.total_tables || 0}
                </p>
              </div>
              
              <div className="p-4 bg-purple-50 rounded-lg border border-purple-200">
                <p className="text-sm font-medium text-purple-900">Validation Issues</p>
                <p className="text-2xl font-bold text-purple-600 mt-1">
                  {displayResult.result?.summary?.validation_issues?.total_issues || 0}
                </p>
              </div>
            </div>

            {/* Download Links */}
            <div className="space-y-3">
              <h3 className="text-lg font-semibold text-slate-900 mb-4">Download Results</h3>
              
              {displayResult.downloads && (
                <>
                  {displayResult.downloads.normalized_text && (
                  <button
                    onClick={() => handleDownload(displayResult.downloads!.normalized_text!, 'normalized_document.txt')}
                    className="w-full flex items-center justify-between p-4 bg-slate-50 hover:bg-slate-100 rounded-lg border border-slate-200 transition-colors"
                  >
                    <div className="flex items-center">
                      <svg className="w-6 h-6 text-slate-600 mr-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                      </svg>
                      <span className="font-medium text-slate-900">Normalized Document (TXT)</span>
                    </div>
                    <svg className="w-5 h-5 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                    </svg>
                  </button>
                  )}

                  {displayResult.downloads.clauses_json && (
                  <button
                    onClick={() => handleDownload(displayResult.downloads!.clauses_json!, 'clauses.json')}
                    className="w-full flex items-center justify-between p-4 bg-slate-50 hover:bg-slate-100 rounded-lg border border-slate-200 transition-colors"
                  >
                    <div className="flex items-center">
                      <svg className="w-6 h-6 text-slate-600 mr-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z" />
                      </svg>
                      <span className="font-medium text-slate-900">Clauses Data (JSON)</span>
                    </div>
                    <svg className="w-5 h-5 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                    </svg>
                  </button>
                  )}

                  {displayResult.downloads.tables_json && (
                  <button
                    onClick={() => handleDownload(displayResult.downloads!.tables_json!, 'tables.json')}
                    className="w-full flex items-center justify-between p-4 bg-slate-50 hover:bg-slate-100 rounded-lg border border-slate-200 transition-colors"
                  >
                    <div className="flex items-center">
                      <svg className="w-6 h-6 text-slate-600 mr-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 10h18M3 14h18m-9-4v8m-7 0h14a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" />
                      </svg>
                      <span className="font-medium text-slate-900">Tables Data (JSON)</span>
                    </div>
                    <svg className="w-5 h-5 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                    </svg>
                  </button>
                  )}
                </>
              )}
            </div>

            {/* Processing Details */}
            {displayResult.result?.summary && (
              <div className="mt-8 p-4 bg-slate-50 rounded-lg border border-slate-200">
                <h4 className="text-sm font-semibold text-slate-700 mb-2">Document Information</h4>
                <dl className="space-y-1 text-sm">
                  <div className="flex justify-between">
                    <dt className="text-slate-600">Document Title:</dt>
                    <dd className="font-medium text-slate-900">{displayResult.result.summary.document_title}</dd>
                  </div>
                  {displayResult.result.summary.validation_issues && (
                    <>
                      <div className="flex justify-between">
                        <dt className="text-slate-600">Errors:</dt>
                        <dd className="font-medium text-red-600">{displayResult.result.summary.validation_issues.errors}</dd>
                      </div>
                      <div className="flex justify-between">
                        <dt className="text-slate-600">Warnings:</dt>
                        <dd className="font-medium text-yellow-600">{displayResult.result.summary.validation_issues.warnings}</dd>
                      </div>
                    </>
                  )}
                </dl>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Footer */}
      <footer className="border-t border-slate-200 mt-16 py-8 bg-white">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8">
          <p className="text-center text-sm text-slate-600">
            PDF Structure Extraction Pipeline • Built with local pdfplumber extraction
          </p>
        </div>
      </footer>
    </main>
  )
}
