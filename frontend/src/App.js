import { useState } from "react";
import axios from "axios";
import "./App.css";
import { Authenticator } from "@aws-amplify/ui-react";
import { Amplify } from "aws-amplify";
import { fetchAuthSession } from "aws-amplify/auth";

Amplify.configure({
  Auth: {
    Cognito: {
      userPoolClientId: process.env.REACT_APP_USERPOOL_CLIENTID,
      userPoolId: process.env.REACT_APP_USERPOOL_ID,
      region: process.env.REACT_APP_REGION
    },
  }
});

function App() {
  const [licenseFile, setLicenseFile] = useState(null);
  const [selfieFile, setSelfieFile] = useState(null);
  const [licenseFileName, setLicenseFileName] = useState("No file chosen");
  const [selfieFileName, setSelfieFileName] = useState("No file chosen");
  const [count, setCount] = useState(0);

  const API_URL = `${process.env.REACT_APP_API_URL}/id-verify`;

  const convertToBase64 = (file) => {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.readAsDataURL(file);
      reader.onload = () => resolve(reader.result.split(",")[1]);
      reader.onerror = (error) => reject(error);
    });
  };

  const uploadFiles = async () => {
    if (!licenseFile || !selfieFile) {
      alert("Please select both a driver's license and a selfie.");
      return;
    }
  
    try {
      console.log('1. Starting upload process...');
      
      const { tokens } = await fetchAuthSession();
      const token = tokens.idToken.toString();
      
      const licenseBase64 = await convertToBase64(licenseFile);
      const selfieBase64 = await convertToBase64(selfieFile);
      
      const headers = {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${token}`,
        "x-api-key": process.env.REACT_APP_API_KEY
      };
  
      console.log('Request details:', {
        url: API_URL,
        headerKeys: Object.keys(headers),
        apiKeyPresent: !!headers['x-api-key']
      });
  
      const response = await axios({
        method: 'post',
        url: API_URL,
        data: {
          dl: licenseBase64,
          selfie: selfieBase64,
        },
        headers: headers,
        timeout: 30000
      });
  
      console.log('Raw response data:', JSON.stringify(response.data, null, 2));
      console.log('Response received:', {
        status: response.status,
        statusText: response.statusText,
        data: response.data
      });
  
      // Handle the response data
      if (response.status === 200) {
        let resultData;
        
        // Check if response.data is a string that needs parsing
        if (typeof response.data === 'string') {
          resultData = JSON.parse(response.data);
        } else {
          resultData = response.data;
        }
  
        // Check if there's a nested body that needs parsing
        if (resultData.body && typeof resultData.body === 'string') {
          resultData = JSON.parse(resultData.body);
        }
  
        console.log('Processed response data:', resultData);
  
        if (resultData.verificationId) {
          const message = `Verification ID: ${resultData.verificationId}\n` +
                         `Status: ${resultData.status}\n` +
                         `Timestamp: ${resultData.timestamp}`;
          alert(message);
        } else {
          throw new Error('Missing verification ID in response');
        }
      } else {
        throw new Error(`Unexpected status code: ${response.status}`);
      }
  
    } catch (error) {
      console.error('Upload error:', {
        name: error.name,
        message: error.message,
        response: error.response ? {
          status: error.response.status,
          data: error.response.data
        } : 'No response data'
      });
  
      if (error.response) {
        // The request was made and the server responded with a status code
        // that falls out of the range of 2xx
        console.error("Error response details:", {
          data: error.response.data,
          status: error.response.status,
          headers: error.response.headers
        });
        alert(`Server error: ${
          error.response.data.error || 
          (error.response.data.body && JSON.parse(error.response.data.body).error) || 
          "Unknown error"
        }`);
      } else if (error.request) {
        // The request was made but no response was received
        console.error("No response received:", {
          url: API_URL,
          method: "POST"
        });
        alert(
          "The server did not respond. Please try again or contact support if the problem persists."
        );
      } else {
        // Something happened in setting up the request that triggered an Error
        console.error("Request setup error:", error.message);
        alert("Error setting up the request: " + error.message);
      }
    }
  };
  
  const handleLicenseChange = (e) => {
    const file = e.target.files[0];
    setLicenseFile(file);
    setLicenseFileName(file ? file.name : "No file chosen");
  };

  const handleSelfieChange = (e) => {
    const file = e.target.files[0];
    setSelfieFile(file);
    setSelfieFileName(file ? file.name : "No file chosen");
  };

  const formFields = {
    signUp: {
      email: {
        order: 1,
      },
      username: {
        order: 2,
      },
      password: {
        order: 3,
      },
      confirm_password: {
        order: 4,
      },
    },
  };

  return (
    <Authenticator formFields={formFields}>
      {({ signOut, user }) => (
        <div className="App">
          <header className="App-header">
            <h1>Hello {user?.username}</h1>
            <button onClick={signOut} className="sign-out-btn">
              Sign out
            </button>
          </header>

          <main className="app-main">
            <div className="upload-container">
              <div className="upload-box">
                <h3>Upload Driver's License</h3>
                <input
                  type="file"
                  id="license-file"
                  className="file-input"
                  onChange={handleLicenseChange}
                  accept="image/*"
                />
                <label htmlFor="license-file" className="file-label">
                  Choose File
                </label>
                <div className="file-name">{licenseFileName}</div>
              </div>

              <div className="upload-box">
                <h3>Upload Self-picture (Selfie)</h3>
                <input
                  type="file"
                  id="selfie-file"
                  className="file-input"
                  onChange={handleSelfieChange}
                  accept="image/*"
                />
                <label htmlFor="selfie-file" className="file-label">
                  Choose File
                </label>
                <div className="file-name">{selfieFileName}</div>
              </div>
            </div>

            <button className="verify-button" onClick={uploadFiles}>
              Verify Identity
            </button>
          </main>
        </div>
      )}
    </Authenticator>
  );
}
export default App;