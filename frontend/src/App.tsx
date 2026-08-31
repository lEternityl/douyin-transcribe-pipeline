import { Layout, Menu } from "antd";
import { NavLink, Route, Routes, useLocation } from "react-router-dom";
import UsersPage from "./pages/UsersPage";
import UserDetailPage from "./pages/UserDetailPage";
import TasksPage from "./pages/TasksPage";
import SettingsPage from "./pages/SettingsPage";

const { Header, Sider, Content } = Layout;

const items = [
  { key: "/users", label: <NavLink to="/users">用户</NavLink> },
  { key: "/tasks", label: <NavLink to="/tasks">任务</NavLink> },
  { key: "/settings", label: <NavLink to="/settings">设置</NavLink> },
];

export default function App() {
  const loc = useLocation();
  const selected = "/" + (loc.pathname.split("/")[1] || "users");

  return (
    <Layout style={{ minHeight: "100vh" }}>
      <Sider theme="light" width={180}>
        <div style={{ padding: "20px 16px", fontWeight: 600, fontSize: 16 }}>
          抖音流水线
        </div>
        <Menu mode="inline" selectedKeys={[selected]} items={items} />
      </Sider>
      <Layout>
        <Header style={{ background: "#fff", padding: "0 24px" }}>
          <h3 style={{ margin: 0, lineHeight: "64px" }}>抖音 MP3 下载 / 转写</h3>
        </Header>
        <Content style={{ padding: 24 }}>
          <Routes>
            <Route path="/" element={<UsersPage />} />
            <Route path="/users" element={<UsersPage />} />
            <Route path="/users/:id" element={<UserDetailPage />} />
            <Route path="/tasks" element={<TasksPage />} />
            <Route path="/settings" element={<SettingsPage />} />
          </Routes>
        </Content>
      </Layout>
    </Layout>
  );
}
