import ApartmentIcon from "@mui/icons-material/ApartmentOutlined";
import AutoAwesomeIcon from "@mui/icons-material/AutoAwesomeOutlined";
import BookmarkIcon from "@mui/icons-material/BookmarkBorderOutlined";
import DictionaryIcon from "@mui/icons-material/MenuBookOutlined";
import InsightsIcon from "@mui/icons-material/InsightsOutlined";
import InventoryIcon from "@mui/icons-material/Inventory2Outlined";
import LogoutIcon from "@mui/icons-material/LogoutOutlined";
import RadarIcon from "@mui/icons-material/RadarOutlined";
import SettingsIcon from "@mui/icons-material/SettingsOutlined";
import SourceIcon from "@mui/icons-material/SettingsInputAntennaOutlined";
import ViewKanbanIcon from "@mui/icons-material/ViewKanbanOutlined";
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
import type { ReactNode } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";

import { logout } from "@/api/auth";
import { useSession } from "@/hooks/useSession";

const NAV_WIDTH = 252;

interface NavItem {
  label: string;
  to: string;
  icon: ReactNode;
}

interface NavSection {
  label: string;
  items: NavItem[];
}

// 구현스펙 02절 pages/ 목록 + 오늘 결정사항(S7→고객 관심주제 관리, S9 카탈로그 신설) 반영.
// 실제 화면은 U4 이후에 채워지고, 지금은 셸+라우팅만(U3 범위).
const NAV_SECTIONS: NavSection[] = [
  {
    label: "공고",
    items: [
      { label: "공고 탐색", to: "/notices", icon: <RadarIcon fontSize="small" /> },
      { label: "심층 분석", to: "/analyses", icon: <AutoAwesomeIcon fontSize="small" /> },
      { label: "파이프라인", to: "/pipeline", icon: <ViewKanbanIcon fontSize="small" /> },
      { label: "기관 프로파일", to: "/orgs", icon: <ApartmentIcon fontSize="small" /> },
      { label: "시장 분석", to: "/analytics", icon: <InsightsIcon fontSize="small" /> },
    ],
  },
  {
    label: "고객 관리",
    items: [
      { label: "고객 관심 주제", to: "/customers/interests", icon: <BookmarkIcon fontSize="small" /> },
    ],
  },
  {
    label: "관리",
    items: [
      { label: "소스 관리", to: "/admin/sources", icon: <SourceIcon fontSize="small" /> },
      { label: "키워드 사전", to: "/admin/keywords", icon: <DictionaryIcon fontSize="small" /> },
      { label: "제품 카탈로그", to: "/admin/products", icon: <InventoryIcon fontSize="small" /> },
      { label: "감사 로그", to: "/admin/audit", icon: <SettingsIcon fontSize="small" /> },
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
          borderRight: "1px dashed",
          borderColor: "grey.300",
          p: 2,
          position: "sticky",
          top: 0,
          height: "100vh",
          display: "flex",
          flexDirection: "column",
        }}
      >
        <Stack direction="row" spacing={1.25} alignItems="center" sx={{ px: 1, pb: 2.5 }}>
          <Box
            sx={{
              width: 34,
              height: 34,
              borderRadius: "10px",
              display: "grid",
              placeItems: "center",
              color: "#fff",
              fontWeight: 700,
              background: (theme) =>
                `linear-gradient(135deg, ${theme.palette.primary.main}, ${theme.palette.primary.dark})`,
            }}
          >
            B
          </Box>
          <Box>
            <Typography fontWeight={700} sx={{ letterSpacing: "-0.02em" }}>
              BidRadar
            </Typography>
            <Typography variant="caption" color="text.secondary">
              입찰 레이더
            </Typography>
          </Box>
        </Stack>

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
                  sx={{
                    borderRadius: 1,
                    mb: 0.25,
                    "&.active": {
                      bgcolor: "primary.lighter",
                      color: "primary.dark",
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
          <Divider sx={{ borderStyle: "dashed", mb: 1.5 }} />
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
