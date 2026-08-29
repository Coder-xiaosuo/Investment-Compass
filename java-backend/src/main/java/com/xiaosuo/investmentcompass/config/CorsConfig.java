package com.xiaosuo.investmentcompass.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.CorsRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

/**
 * 跨域配置
 * <p>
 * 允许所有来源的跨域请求，用于前端开发调试。
 * 生产环境下应限制 allowedOriginPatterns 为具体域名。
 */
@Configuration
public class CorsConfig {

    /**
     * 配置跨域映射
     * <p>
     * 允许所有路径、所有HTTP方法、所有请求头，
     * 支持凭证传递，预检请求缓存1小时。
     */
    @Bean
    public WebMvcConfigurer corsConfigurer() {
        return new WebMvcConfigurer() {
            @Override
            public void addCorsMappings(CorsRegistry registry) {
                registry.addMapping("/**")
                        .allowedOriginPatterns("*")
                        .allowedMethods("*")
                        .allowedHeaders("*")
                        .allowCredentials(true)
                        .maxAge(3600);
            }
        };
    }
}
