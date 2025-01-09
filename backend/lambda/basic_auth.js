function handler(event) {
    var request = event.request;
    var headers = request.headers;
  
    // basic auth
    var authUser = 'demo'; 
    var authPass = 'demo'; 
    var authString = 'Basic ' + (authUser + ':' + authPass).toString('base64');
  
    if (typeof headers.authorization == 'undefined' || headers.authorization.value != authString) {
        var response = {
            statusCode: 401,
            statusDescription: 'Unauthorized',
            headers: {
                'www-authenticate': {
                    'value' : 'Basic realm="Enter credentials."'
                }
            }
        };
        return response;
    }
  
    return request;
  }