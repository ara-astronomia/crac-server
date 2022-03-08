/* Java Script */
var Out;
var dRa = "{ra}"; 
var dDec = "{dec}";
var name = "park sync";
sky6RASCOMTele.Asynchronous = true;
sky6RASCOMTele.Connect();

if (sky6RASCOMTele.IsConnected)
{{
    sky6RASCOMTele.Sync(dRa, dDec, name);
    obj = {{
		az: 0,
		alt: 0,
		tr: sky6RASCOMTele.IsTracking,
		sl: sky6RASCOMTele.IsSlewComplete
  	}};
	Out = JSON.stringify(obj);
}}
