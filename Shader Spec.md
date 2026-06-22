> Auto-generated from `graphics/SHADER_SPEC.md` in the docs repo.

# Color Correction Effect Shader Specification

## Overview
The Color Correction Effect allows users to adjust the color balance, contrast, brightness, and saturation of video clips in real-time. This effect leverages GPU shaders to ensure high performance and smooth playback.

## Shader Stages

### Vertex Shader
The vertex shader is responsible for transforming the vertex positions and passing the texture coordinates to the fragment shader.

```hlsl
cbuffer ConstantBuffer : register(b0)
{
    float4x4 projectionMatrix;
    float2 textureSize;
}

struct VS_INPUT
{
    float3 position : POSITION;
    float2 texCoord : TEXCOORD;
};

struct VS_OUTPUT
{
    float4 position : SV_POSITION;
    float2 texCoord : TEXCOORD;
};

VS_OUTPUT main(VS_INPUT input)
{
    VS_OUTPUT output;
    output.position = mul(projectionMatrix, float4(input.position, 1.0f));
    output.texCoord = input.texCoord;
    return output;
}
```

### Fragment Shader
The fragment shader applies the color correction adjustments to each pixel. It uses the following parameters:
- **Brightness**: Adjusts the overall brightness of the image.
- **Contrast**: Adjusts the difference between the darkest and lightest parts of the image.
- **Saturation**: Adjusts the intensity of colors.
- **Temperature**: Adjusts the color temperature to make the image warmer or cooler.
- **Tint**: Adjusts the green-magenta balance.

```hlsl
Texture2D shaderTexture : register(t0);
SamplerState samplerState : register(s0);

cbuffer ColorCorrectionBuffer : register(b0)
{
    float brightness;
    float contrast;
    float saturation;
    float temperature;
    float tint;
}

struct PS_INPUT
{
    float4 position : SV_POSITION;
    float2 texCoord : TEXCOORD;
};

float3 AdjustColor(float3 color, float brightness, float contrast, float saturation, float temperature, float tint)
{
    // Apply brightness
    color += brightness;

    // Apply contrast
    color = (color - 0.5f) * contrast + 0.5f;

    // Convert to HSV
    float3 hsv = RGBtoHSV(color);

    // Apply saturation
    hsv.y *= saturation;

    // Convert back to RGB
    color = HSVtoRGB(hsv);

    // Apply temperature and tint
    float3x3 temperatureMatrix = float3x3(
        1.0f, 0.0f, 0.0f,
        0.0f, 1.0f, 0.0f,
        temperature, tint, 1.0f
    );
    color = mul(temperatureMatrix, color);

    return color;
}

float3 RGBtoHSV(float3 c)
{
    float4 K = float4(0.0f, -1.0f / 3.0f, 2.0f / 3.0f, -1.0f);
    float4 p = lerp(float4(c.bg, K.wz), float4(c.gb, K.xy), step(c.b, c.g));
    float4 q = lerp(float4(p.xyw, c.r), float4(c.r, p.yzx), step(p.x, c.r));

    float d = q.x - min(q.w, q.y);
    float e = 1.0e-10f;
    return float3(abs(q.z + (q.w - q.y) / (6.0f * d + e)), d / (q.x + e), q.x);
}

float3 HSVtoRGB(float3 c)
{
    float4 K = float4(1.0f, 2.0f / 3.0f, 1.0f / 3.0f, 3.0f);
    float3 p = abs(frac(c.xxx + K.xyz) * 6.0f - K.www);
    return c.z * lerp(K.xxx, clamp(p - K.xxx, 0.0f, 1.0f), c.y);
}

float4 main(PS_INPUT input) : SV_TARGET
{
    float4 color = shaderTexture.Sample(samplerState, input.texCoord);
    float3 correctedColor = AdjustColor(color.rgb, brightness, contrast, saturation, temperature, tint);
    return float4(correctedColor, color.a);
}
```

## Parameters
- **Brightness**: Range [-1.0, 1.0]
- **Contrast**: Range [0.0, 2.0]
- **Saturation**: Range [0.0, 2.0]
- **Temperature**: Range [-1.0, 1.0]
- **Tint**: Range [-1.0, 1.0]

## Integration
The shader is integrated into the rendering pipeline as follows:
1. **Initialization**: Load the shader files and compile them during application startup.
2. **Parameter Binding**: Bind the color correction parameters to the shader constant buffer each frame.
3. **Rendering**: Apply the shader during the rendering of each video frame.

## Performance Considerations
- **GPU Utilization**: The shader is designed to be lightweight to ensure it does not become a bottleneck in the rendering pipeline.
- **Caching**: Reuse shader resources and avoid unnecessary shader compilations at runtime.
- **Threading**: Ensure that parameter updates are thread-safe and do not interfere with rendering operations.

## Example Usage
```cpp
ColorCorrectionEffect colorCorrection;
colorCorrection.SetBrightness(0.1f);
colorCorrection.SetContrast(1.2f);
colorCorrection.SetSaturation(1.1f);
colorCorrection.SetTemperature(0.05f);
colorCorrection.SetTint(-0.05f);

// During rendering
colorCorrection.ApplyEffect(videoFrame);
```

## Conclusion
The Color Correction Effect provides a powerful tool for adjusting the visual characteristics of video content. By leveraging GPU shaders, it ensures that these adjustments are applied efficiently and in real-time, enhancing the overall user experience.