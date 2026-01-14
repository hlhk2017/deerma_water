# 飞利浦水健康集成

Home Assistant 自定义集成，用于控制飞利浦/Deerma 净水器设备。
## 效果图
### 配置后的实体
<img width="1270" height="808" alt="ScreenShot_2026-01-14_202921_609" src="https://github.com/user-attachments/assets/a4c94a22-77be-426c-8f00-0ad62b54975d" />

### 详细的历史数据

<img width="575" height="830" alt="ScreenShot_2026-01-14_203024_290" src="https://github.com/user-attachments/assets/8b238991-cf02-45e3-b932-6c2243c8f122" />

## 功能特性

### 🔐 登录方式
- **密码登录**：使用手机号和密码登录
- **验证码登录**：使用手机号和验证码登录（配置时可选）

### 🎛️ 控制实体
- **水温设置**：选择出水温度（常温、45℃、55℃、65℃、75℃、85℃、95℃、97℃、99℃、100℃等）
- **出水量设置**：选择出水量（200mL、250mL、350mL、500mL、1000mL、1500mL、2000mL等）
- **一键55度按钮**：快速设置水温为55度

### 📊 传感器实体
- **总用水量**：累计总用水量（升）
- **自来水TDS**：自来水TDS值（ppm）
- **净水TDS**：净化后水的TDS值（ppm）
- **AQP滤芯寿命**：AQP滤芯剩余寿命（%）
- **PC5IN1滤芯寿命**：PC5IN1滤芯剩余寿命（%）

### 📈 数据统计
- 日用水量统计
- 周用水量统计
- 月用水量统计
- 平均TDS值

### 🔄 实时更新
- 通过 WebSocket MQTT 实时接收设备状态更新
- API 数据定期更新（30秒间隔）
- 传感器值自动保留，避免显示为"未知"

## 安装

### 方式一：通过 HACS 安装（推荐）

1. 确保已安装 [HACS](https://hacs.xyz/)
2. 在 HACS 中添加自定义仓库
3. 搜索并安装"飞利浦水健康"
4. 重启 Home Assistant
5. 在设置 -> 设备与服务中添加集成

### 方式二：手动安装

1. 将 `deerma_water` 文件夹复制到 `custom_components` 目录
2. 重启 Home Assistant
3. 在设置 -> 设备与服务中添加集成

## 配置

### 首次配置

1. 进入 **设置** -> **设备与服务**
2. 点击 **添加集成**
3. 搜索 **飞利浦水健康**
4. 选择登录方式：
   - **密码登录**：输入手机号和密码
   - **验证码登录**：
     - 先输入手机号，系统会发送验证码
     - 输入收到的验证码完成登录
5. 配置完成后，系统会自动发现设备并创建实体

### 配置参数

- **手机号**：用于登录的手机号码
- **密码**：账户密码（仅密码登录需要）
- **验证码**：短信验证码（仅验证码登录需要）

## 实体说明

### Select 实体

#### 水温设置
- **实体ID**：`select.{device_id}_temperature`
- **名称**：水温设置
- **选项**：根据设备配置显示可用温度选项
  - 常温
  - 45℃、55℃、65℃、75℃、85℃、95℃、97℃、99℃、100℃
  - 5℃（制冷模式）

#### 出水量设置
- **实体ID**：`select.{device_id}_water_volume`
- **名称**：出水量设置
- **选项**：根据设备配置显示可用水量选项
  - 200mL、250mL、350mL、500mL、1000mL、1500mL、2000mL

### Button 实体

#### 一键55度
- **实体ID**：`button.{device_id}_quick_55`
- **名称**：一键55度
- **功能**：快速设置水温为55度

### Sensor 实体

#### 总用水量
- **实体ID**：`sensor.{device_id}_total_water`
- **名称**：总用水量
- **单位**：升（L）
- **状态类**：总计递增

#### 自来水TDS
- **实体ID**：`sensor.{device_id}_tap_water_tds`
- **名称**：自来水TDS
- **单位**：ppm
- **说明**：自来水（未净化）的TDS值

#### 净水TDS
- **实体ID**：`sensor.{device_id}_purified_tds`
- **名称**：净水TDS
- **单位**：ppm
- **说明**：净化后水的TDS值

#### AQP滤芯寿命
- **实体ID**：`sensor.{device_id}_aqp_filter_life`
- **名称**：AQP滤芯寿命
- **单位**：%
- **说明**：AQP滤芯的剩余寿命百分比

#### PC5IN1滤芯寿命
- **实体ID**：`sensor.{device_id}_pc5in1_filter_life`
- **名称**：PC5IN1滤芯寿命
- **单位**：%
- **说明**：PC5IN1滤芯的剩余寿命百分比

## 自动化示例

### 示例1：当滤芯寿命低于20%时发送通知

```yaml
automation:
  - alias: "滤芯寿命提醒"
    trigger:
      - platform: numeric_state
        entity_id: sensor.{device_id}_aqp_filter_life
        below: 20
    action:
      - service: notify.mobile_app_your_phone
        data:
          message: "AQP滤芯寿命已低于20%，请及时更换！"
```

### 示例2：使用一键55度按钮

```yaml
automation:
  - alias: "早上喝温水"
    trigger:
      - platform: time
        at: "07:00:00"
    action:
      - service: button.press
        target:
          entity_id: button.{device_id}_quick_55
```

### 示例3：根据TDS值自动控制

```yaml
automation:
  - alias: "TDS值过高提醒"
    trigger:
      - platform: numeric_state
        entity_id: sensor.{device_id}_tap_water_tds
        above: 300
    action:
      - service: notify.mobile_app_your_phone
        data:
          message: "自来水TDS值过高（{{ states('sensor.{device_id}_tap_water_tds') }}ppm），建议使用净化水"
```

## 技术细节

### 通信方式
- **API**：通过 HTTPS 与飞利浦IoT平台通信
- **MQTT**：通过 WebSocket MQTT 接收实时设备状态更新

### 数据更新
- API 数据更新间隔：30秒
- MQTT 实时更新：设备状态变化时立即推送
- 传感器值保留：当数据暂时不可用时，保留上次有效值

### 支持的设备
- 飞利浦/Deerma 净水器系列
- 支持 AWS IoT Shadow 协议的设备

## 故障排除

### 问题1：无法连接设备
- 检查网络连接
- 确认手机号和密码/验证码正确
- 查看日志文件获取详细错误信息

### 问题2：传感器显示"未知"
- 等待30秒让数据更新
- 检查设备是否在线
- 查看日志确认MQTT连接是否正常

### 问题3：控制无效
- 确认设备在线
- 检查MQTT连接状态
- 查看日志确认命令是否发送成功

### 问题4：验证码收不到
- 确认手机号格式正确
- 检查短信是否被拦截
- 尝试重新请求验证码

## 日志

查看详细日志：
```yaml
logger:
  default: info
  logs:
    custom_components.deerma_water: debug
```

## 版本历史

### v1.0.0
- 初始版本
- 支持密码和验证码登录
- 支持水温、出水量控制
- 支持多个传感器实体
- 支持一键55度按钮
- 实时MQTT状态更新
- 传感器值保留机制

## 贡献

欢迎提交 Issue 和 Pull Request！

## 许可证

MIT License

## 致谢

感谢所有为这个项目做出贡献的开发者！
