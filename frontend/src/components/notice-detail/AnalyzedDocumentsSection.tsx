import { useState } from "react";
import ExpandLessIcon from "@mui/icons-material/ExpandLessOutlined";
import ExpandMoreIcon from "@mui/icons-material/ExpandMoreOutlined";
import { Box, Card, Chip, Collapse, Stack, Typography } from "@mui/material";

import type { ExtractionResult } from "@/api/analysis";

// 첨부분석(A1) 원문 결과 — 예전엔 "공고 상세분석" 카드 안쪽 "첨부분석" 섹션이었으나, 페이지
// 최하단 별도 섹션 "분석대상 파일"로 분리했다(2026-09-08 요청) — AI분석 탭들과 섞이지 않고
// 참고자료로 따로 훑어볼 수 있게. 여기 있는 문서는 전부 실제로 AI분석(A2) 프롬프트에 들어간
// "분석대상" 문서다 — 제출서류·규정·법령·문서양식·사용법·매뉴얼 등 과제 공통 문서는 수집
// 단계(analysis_pilot.py _should_skip_by_name)에서 이미 제외돼 애초에 이 목록에 없다.
export function AnalyzedDocumentsSection({ extraction }: { extraction?: ExtractionResult | null }) {
  if (!extraction) return null;
  const docs = extraction.docs ?? [];

  return (
    <Card sx={{ p: 3 }}>
      <Typography variant="h3" sx={{ mb: 2 }}>
        분석대상 파일
      </Typography>
      {docs.length > 0 ? (
        <Stack spacing={2}>
          <Typography variant="body2" color="text.secondary">
            AI분석 없이 첨부문서에서 텍스트만 추출한 결과입니다(LLM 요약 아님, 원문 그대로).
          </Typography>
          {docs.map((doc, i) => (
            <ExtractedDocItem key={i} doc={doc} />
          ))}
        </Stack>
      ) : (
        <Typography variant="body2" color="text.secondary" sx={{ py: 2 }}>
          첨부문서를 찾지 못했거나 추출된 내용이 없습니다.
        </Typography>
      )}
    </Card>
  );
}

// 원문이 문서마다 길어서 기본으로는 접어두고 필요할 때만 펼쳐 본다(2026-09-07 요청).
function ExtractedDocItem({ doc }: { doc: ExtractionResult["docs"][number] }) {
  const [open, setOpen] = useState(false);
  return (
    <Box sx={{ border: "1px solid", borderColor: "divider", borderRadius: 1, p: 1.5 }}>
      <Stack
        direction="row"
        spacing={1}
        alignItems="center"
        onClick={() => setOpen((v) => !v)}
        sx={{ cursor: "pointer", userSelect: "none" }}
      >
        {open ? <ExpandLessIcon fontSize="small" /> : <ExpandMoreIcon fontSize="small" />}
        <Typography variant="subtitle2" fontWeight={700} sx={{ flex: 1, minWidth: 0 }}>
          {doc.name}
        </Typography>
        <Chip
          label={doc.extract_ok ? "추출 성공" : "추출 실패"}
          size="small"
          color={doc.extract_ok ? "success" : "default"}
          variant="outlined"
        />
      </Stack>
      <Collapse in={open}>
        <Box sx={{ mt: 1 }}>
          {doc.extract_ok && doc.text ? (
            <Box sx={{ maxHeight: 300, overflow: "auto", bgcolor: "action.hover", borderRadius: 1, p: 1 }}>
              <Typography variant="body2" sx={{ whiteSpace: "pre-wrap", fontFamily: "monospace", fontSize: "0.8rem" }}>
                {doc.text}
              </Typography>
            </Box>
          ) : (
            <Typography variant="caption" color="text.secondary">
              {doc.error || "추출된 텍스트가 없습니다."}
            </Typography>
          )}
        </Box>
      </Collapse>
    </Box>
  );
}
