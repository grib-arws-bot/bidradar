import AccountTreeIcon from "@mui/icons-material/AccountTreeOutlined";
import CategoryIcon from "@mui/icons-material/CategoryOutlined";
import CompareArrowsIcon from "@mui/icons-material/CompareArrowsOutlined";
import DescriptionIcon from "@mui/icons-material/DescriptionOutlined";
import HomeIcon from "@mui/icons-material/HomeOutlined";
import LogoutIcon from "@mui/icons-material/LogoutOutlined";
import PeopleIcon from "@mui/icons-material/PeopleAltOutlined";
import RadarIcon from "@mui/icons-material/RadarOutlined";
import SourceIcon from "@mui/icons-material/SettingsInputAntennaOutlined";
import {
  Avatar,
  Box,
  Divider,
  List,
  ListItemButton,
  ListItemIcon,
  ListItemText,
  Stack,
  Typography,
} from "@mui/material";
import { alpha } from "@mui/material/styles";
import type { ReactNode } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";

import { logout } from "@/api/auth";
import Logo from "@/components/Logo";
import { useSession } from "@/hooks/useSession";

const NAV_WIDTH = 300;

interface NavItem {
  label: string;
  to: string;
  icon: ReactNode;
}

interface NavSection {
  label: string;
  items: NavItem[];
}

// 메뉴 재정리(2026-09-05 사용자 지시) — U3 시절의 구현스펙 자리채움(심층분석·파이프라인·
// 기관프로파일·시장분석·키워드사전·제품카탈로그·감사로그)은 Phase 1 범위 밖이라 제거.
// "고객 관심 주제"는 고객 상세(CustomerDetailPage)로 흡수, 리포트는 "보고서 관리"로 분리.
const NAV_SECTIONS: NavSection[] = [
  {
    label: "홈",
    items: [{ label: "전체 현황", to: "/", icon: <HomeIcon fontSize="small" /> }],
  },
  {
    label: "공고",
    items: [{ label: "공고 탐색", to: "/notices", icon: <RadarIcon fontSize="small" /> }],
  },
  {
    label: "고객",
    items: [
      { label: "고객 관리", to: "/customers", icon: <PeopleIcon fontSize="small" /> },
      { label: "보고서 관리", to: "/customers/reports", icon: <DescriptionIcon fontSize="small" /> },
    ],
  },
  {
    label: "관리",
    items: [
      { label: "공고데이터 수집", to: "/admin/channels", icon: <SourceIcon fontSize="small" /> },
      { label: "공고기관 현황", to: "/admin/agencies", icon: <AccountTreeIcon fontSize="small" /> },
      { label: "관심주제 분류", to: "/admin/topics", icon: <CategoryIcon fontSize="small" /> },
      { label: "매칭 방식 비교", to: "/admin/matching-comparison", icon: <CompareArrowsIcon fontSize="small" /> },
    ],
  },
];

export function DashboardLayout() {
  const navigate = useNavigate();
  const { data: session } = useSession();

  const handleLogout = async () => {
    await logout();
    navigate("/login", { replace: true });
  };

  return (
    <Box sx={{ display: "flex", minHeight: "100vh" }}>
      <Box
        component="nav"
        sx={{
          width: NAV_WIDTH,
          flex: `0 0 ${NAV_WIDTH}px`,
          bgcolor: "background.paper",
          borderRight: "1px solid",
          borderColor: (theme) => alpha(theme.palette.grey[500], 0.12),
          p: 2,
          position: "sticky",
          top: 0,
          height: "100vh",
          display: "flex",
          flexDirection: "column",
        }}
      >
        <Box sx={{ px: 1, pb: 2.5 }}>
          <Logo size={34} showSub />
        </Box>

        {NAV_SECTIONS.map((section) => (
          <Box key={section.label} sx={{ mb: 1 }}>
            <Typography
              variant="overline"
              sx={{ px: 1.25, color: "grey.500", fontWeight: 700, letterSpacing: "0.06em" }}
            >
              {section.label}
            </Typography>
            <List dense disablePadding>
              {section.items.map((item) => (
                <ListItemButton
                  key={item.to}
                  component={NavLink}
                  to={item.to}
                  end={item.to === "/" || item.to === "/customers"}
                  sx={{
                    borderRadius: 1,
                    mb: 0.25,
                    "&.active": {
                      bgcolor: (theme) => alpha(theme.palette.primary.main, 0.08),
                      color: "primary.main",
                      fontWeight: 600,
                    },
                  }}
                >
                  <ListItemIcon sx={{ minWidth: 32, color: "inherit" }}>{item.icon}</ListItemIcon>
                  <ListItemText primaryTypographyProps={{ fontSize: 14 }}>{item.label}</ListItemText>
                </ListItemButton>
              ))}
            </List>
          </Box>
        ))}

        <Box sx={{ mt: "auto" }}>
          <Divider sx={{ mb: 1.5 }} />
          <Stack direction="row" spacing={1.25} alignItems="center" sx={{ px: 1 }}>
            <Avatar sx={{ width: 34, height: 34, bgcolor: "secondary.main", fontSize: 13 }}>
              {session?.email?.[0]?.toUpperCase() ?? "?"}
            </Avatar>
            <Box sx={{ minWidth: 0, flex: 1 }}>
              <Typography variant="body2" noWrap>
                {session?.email}
              </Typography>
            </Box>
            <ListItemButton onClick={handleLogout} sx={{ width: "auto", borderRadius: 1, p: 1 }}>
              <LogoutIcon fontSize="small" />
            </ListItemButton>
          </Stack>
        </Box>
      </Box>

      <Box component="main" sx={{ flex: 1, p: 4, minWidth: 0 }}>
        <Outlet />
      </Box>
    </Box>
  );
}
