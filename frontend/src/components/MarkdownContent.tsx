import { Box, Divider, Link, List, ListItem, Typography } from "@mui/material";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

// AI가 생성한 마크다운(고객 프로필 요약·리포트 AI 코멘트·사업 추진 전략 등)을 앱 타이포그래피에
// 맞춰 렌더링(2026-09-05 요청 — 이전엔 "# ##  **" 원문 기호가 그대로 보이는 raw pre-wrap
// 텍스트였음). react-markdown은 HTML을 직접 주입하지 않아(dangerouslySetInnerHTML 없음) LLM
// 출력이라도 XSS 위험이 없다.
export function MarkdownContent({ children }: { children: string }) {
  return (
    <Box
      sx={{
        "& > :first-of-type": { mt: 0 },
        "& > :last-child": { mb: 0 },
      }}
    >
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          h1: ({ children }) => (
            <Typography variant="h2" sx={{ mt: 3, mb: 1.5 }}>
              {children}
            </Typography>
          ),
          h2: ({ children }) => (
            <Typography variant="h3" sx={{ mt: 3, mb: 1 }}>
              {children}
            </Typography>
          ),
          h3: ({ children }) => (
            <Typography variant="subtitle1" fontWeight={700} sx={{ mt: 2, mb: 1 }}>
              {children}
            </Typography>
          ),
          p: ({ children }) => (
            <Typography variant="body2" sx={{ mb: 1.5, lineHeight: 1.7 }}>
              {children}
            </Typography>
          ),
          ul: ({ children }) => (
            <List dense disablePadding sx={{ mb: 1.5, pl: 2, listStyleType: "disc" }}>
              {children}
            </List>
          ),
          ol: ({ children }) => (
            <Box component="ol" sx={{ mb: 1.5, pl: 3 }}>
              {children}
            </Box>
          ),
          li: ({ children }) => (
            <ListItem disablePadding sx={{ display: "list-item", py: 0.25 }}>
              <Typography variant="body2" component="span" sx={{ lineHeight: 1.7 }}>
                {children}
              </Typography>
            </ListItem>
          ),
          strong: ({ children }) => (
            <Typography component="strong" fontWeight={700}>
              {children}
            </Typography>
          ),
          a: ({ href, children }) => (
            <Link href={href} target="_blank" rel="noreferrer">
              {children}
            </Link>
          ),
          hr: () => <Divider sx={{ my: 2 }} />,
          table: ({ children }) => (
            <Box sx={{ overflowX: "auto", mb: 1.5 }}>
              <Box
                component="table"
                sx={{ borderCollapse: "collapse", width: "100%", "& th, & td": { border: "1px solid", borderColor: "divider", p: 1, fontSize: 14 } }}
              >
                {children}
              </Box>
            </Box>
          ),
        }}
      >
        {children}
      </ReactMarkdown>
    </Box>
  );
}
