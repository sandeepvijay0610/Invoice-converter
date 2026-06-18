export interface InvoiceSummary {
  id: string;
  status: 'PENDING' | 'PROCESSING' | 'READY_FOR_SAP' | 'REQUIRES_MANUAL_REVIEW' | 'FAILED' | 'RATE_LIMITED';
  vendorName: string | null;
  totalAmount: number | null;
  companyCode: string | null;
  createdAt: string;
}

export interface HeaderData {
  vendor_name: string | null;
  vendor_gstin: string | null;
  buyer_name: string | null;
  buyer_gstin: string | null;
  invoice_number: string | null;
  invoice_date: string | null;
  po_number: string | null;
}

export interface FinancialData {
  base_amount: number | null;
  cgst_amount: number | null;
  sgst_amount: number | null;
  igst_amount: number | null;
  total_invoice_amount: number | null;
  tax_code: string | null;
}

export interface LineItem {
  invoice_item_text: string | null;
  hsn_sac_code: string | null;
  quantity: number | null;
  unit_price: number | null;
  line_amount: number | null;
}

export interface ExtractedPayload {
  doc_id: string;
  status: string;
  overall_confidence: number;
  header_data: HeaderData;
  financial_data: FinancialData;
  line_item_data: LineItem[];
}

export interface InvoiceDetail extends InvoiceSummary {
  filePath: string;
  extractedPayload: ExtractedPayload | null;
}

export interface PaginatedResponse {
  items: InvoiceSummary[];
  page: number;
  size: number;
  totalItems: number;
  totalPages: number;
}

export interface UploadResponse {
  id: string;
  uploadUrl: string;
}

export interface StatsResponse {
  total: number;
  readyForSAP: number;
  processing: number;
  needsReview: number;
  failed: number;
}