import { useState } from "react";
import {
  App as AntdApp,
  Button,
  Card,
  Input,
  Space,
  Statistic,
  Typography,
} from "antd";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";

const { Text, Paragraph } = Typography;

export default function SettingsPage() {
  const qc = useQueryClient();
  const { message } = AntdApp.useApp();
  const [content, setContent] = useState("");

  const { data: status } = useQuery({
    queryKey: ["cookie-status"],
    queryFn: api.cookieStatus,
  });

  const saveMutation = useMutation({
    mutationFn: (c: string) => api.setCookie(c),
    onSuccess: (s) => {
      message.success(`Cookie 已保存 (${s.format} 格式, ${s.length} 字符)`);
      qc.invalidateQueries({ queryKey: ["cookie-status"] });
    },
    onError: (e: Error) => message.error(`保存失败: ${e.message}`),
  });

  return (
    <div style={{ maxWidth: 800 }}>
      <Card title="Cookie 状态" style={{ marginBottom: 16 }}>
        <Space size="large">
          <Statistic
            title="已加载"
            value={status?.loaded ? "是" : "否"}
            valueStyle={{ color: status?.loaded ? "#3f8600" : "#cf1322" }}
          />
          <Statistic title="格式" value={status?.format || "-"} />
          <Statistic title="字符数" value={status?.length ?? 0} />
        </Space>
        {status?.preview && (
          <Paragraph type="secondary" style={{ marginTop: 12 }}>
            预览: {status.preview}
          </Paragraph>
        )}
      </Card>

      <Card title="设置 Cookie">
        <Paragraph type="secondary">
          支持两种格式(自动识别):
          <br />
          1. JSON 数组(Cookie-Editor 导出): <Text code>[&#123;"name":"ttwid","value":"xxx"&#125;]</Text>
          <br />
          2. 原始字符串: <Text code>ttwid=xxx; msToken=yyy; ...</Text>
        </Paragraph>
        <Input.TextArea
          rows={8}
          value={content}
          onChange={(e) => setContent(e.target.value)}
          placeholder="粘贴 cookie 内容..."
        />
        <Space style={{ marginTop: 12 }}>
          <Button
            type="primary"
            disabled={!content.trim()}
            loading={saveMutation.isPending}
            onClick={() => saveMutation.mutate(content)}
          >
            保存
          </Button>
        </Space>
      </Card>
    </div>
  );
}
