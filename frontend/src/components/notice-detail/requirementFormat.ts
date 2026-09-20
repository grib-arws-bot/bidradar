import { type Requirement } from "@/api/analysis";

// AnalysisTabsSection(A2 확정 결과)과 SllmPreviewInline(sLLM 미리보기) 둘 다 같은 모양의
// Requirement를 표시하므로 공유한다 — 두 파일이 서로를 import하는 순환 참조를 피하기 위해
// 별도 유틸로 뺐다.
const OP_LABEL: Record<string, string> = { gte: "이상", lte: "이하", eq: "일치", contains: "포함", manual: "서술형" };

export function requirementValueLabel(req: Requirement): string {
  return req.req_value ? `${req.req_value}${req.req_unit ?? ""} ${OP_LABEL[req.op]}` : OP_LABEL[req.op];
}
