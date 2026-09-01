import { Stack, Typography } from "@mui/material";

export function ComingSoonPage({ title }: { title: string }) {
  return (
    <Stack spacing={1} sx={{ py: 10, alignItems: "center", textAlign: "center" }}>
      <Typography variant="h3">{title}</Typography>
      <Typography variant="body2" color="text.secondary">
        다음 작업 단위에서 구현됩니다.
      </Typography>
    </Stack>
  );
}
