* Behavioral ADC chain for ngspice (reference snapshot)
* Matches veriloga/configurable_adc.va and Python noise.py signal order:
*   jitter (in PWL stimulus) -> gain/offset -> nonlinearity -> thermal
*   -> DNL (Python post-process when enabled) -> quantize
*
* Generated netlists with CLI parameters are written to <output-dir>/ngspice/.

Bgain v_gain 0 V={ GAIN*V(vin)+OFFSET_V }
Bnonlin v_nl 0 V={
+  V(v_gain) + VFS*(NONLINEARITY_A2*pow((V(v_gain)-VCM)/VFS,2)
+  + NONLINEARITY_A3*pow((V(v_gain)-VCM)/VFS,3))
+}
Btherm v_th 0 V={ V(v_nl) + SIGMA_THERMAL*agauss(0,1,1) }
Bquant v_code 0 V={
+ ( V(v_th) <= VREFN ? 0 :
+   V(v_th) >= VREFP ? MAXCODE :
+   floor((V(v_th)-VREFN)/LSB+0.5) ) * LSB
+ }
Bclk clk_int 0 V={ 0.5*(1+sgn(sin(2*3.141592653589793*FS*time))) }
