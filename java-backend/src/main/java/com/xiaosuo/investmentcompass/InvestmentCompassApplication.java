package com.xiaosuo.investmentcompass;

import org.mybatis.spring.annotation.MapperScan;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
@MapperScan("com.xiaosuo.investmentcompass.mapper")
public class InvestmentCompassApplication {

    public static void main(String[] args) {
        SpringApplication.run(InvestmentCompassApplication.class, args);
    }

}
