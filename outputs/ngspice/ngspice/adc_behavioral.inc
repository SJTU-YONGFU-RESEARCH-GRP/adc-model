* Behavioral ADC through nonlinearity (matches veriloga/configurable_adc.va)
Bgain v_gain 0 V={ GAIN*V(vin)+OFFSET_V }
Bnonlin v_nl 0 V={
+  V(v_gain) + VFS*(NONLINEARITY_A2*pow((V(v_gain)-VCM)/VFS,2)
+  + NONLINEARITY_A3*pow((V(v_gain)-VCM)/VFS,3))
+}

Vclk clk_int 0 PULSE(0 1 0 100p 100p {0.5/1000000.0} {1/1000000.0})
