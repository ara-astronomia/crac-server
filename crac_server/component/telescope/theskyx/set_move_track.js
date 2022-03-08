/* Java Script */
var Out;
var TargetAz = "{az}";
var TargetAlt = "{alt}";
var Track = "{tr}";
sky6RASCOMTele.Asynchronous = true;
sky6RASCOMTele.Connect();

if (sky6RASCOMTele.IsConnected)
{{
  if (TargetAlt && TargetAz) {{
	  sky6RASCOMTele.SlewToAzAlt(TargetAz, TargetAlt, "");
  }}
  sky6RASCOMTele.SetTracking(Track, 1, 0, 0);
  Out = sky6RASCOMTele.LastSlewError();
}}
