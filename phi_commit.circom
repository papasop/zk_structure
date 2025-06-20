pragma circom 2.0.0;

template PhiCommit(n) {
    signal input A[n];
    signal input B[n];
    signal output out;
    signal terms[n];
    signal acc[n+1]; // Use an array for the accumulator

    acc[0] <== 0; // Initialize the first element

    for (var i = 0; i < n; i++) {
        terms[i] <== A[i] + B[i];
        acc[i+1] <== acc[i] + terms[i]; // Accumulate in the next element of the array
    }

    out <== acc[n]; // The final sum is in the last element
}

component main = PhiCommit(4);
