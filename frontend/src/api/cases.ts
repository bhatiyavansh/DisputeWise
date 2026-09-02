import { apiRequest } from './client'
import type { CaseDetail, CaseListFilters, CaseListItem, EvidenceItem, Page } from './types'

export function listCases(filters: CaseListFilters = {}, signal?: AbortSignal): Promise<Page<CaseListItem>> {
  return apiRequest<Page<CaseListItem>>('/cases', {
    query: {
      page: filters.page,
      page_size: filters.page_size,
      reason_code: filters.reason_code,
      status: filters.status,
    },
    signal,
  })
}

export function getCase(caseId: string, signal?: AbortSignal): Promise<CaseDetail> {
  return apiRequest<CaseDetail>(`/cases/${encodeURIComponent(caseId)}`, { signal })
}

export function getCaseEvidence(caseId: string, signal?: AbortSignal): Promise<EvidenceItem[]> {
  return apiRequest<EvidenceItem[]>(`/cases/${encodeURIComponent(caseId)}/evidence`, { signal })
}
