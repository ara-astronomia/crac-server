/* Java Script */
var Out;

sky6RASCOMTele.Connect();

if (sky6RASCOMTele.IsConnected)
{
	sky6RASCOMTele.GetAzAlt();
	obj = {
		az: sky6RASCOMTele.dAz,
		alt: sky6RASCOMTele.dAlt,
		tr: sky6RASCOMTele.IsTracking,
		sl: sky6RASCOMTele.IsSlewComplete
  	};
	Out = JSON.stringify(obj);
}
